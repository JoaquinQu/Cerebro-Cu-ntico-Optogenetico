"""Servidor HTTP: API JSON + archivos del frontend.

Rutas
    GET  /api/health                     estado y si IonQ está configurado
    GET  /api/connectome                 neuronas (posición, tipo, grado) y aristas
    POST /api/walk                       quantum walk exacto en las 302 neuronas
    GET  /api/microcircuits              microcircuitos predefinidos
    POST /api/microcircuit/simulate      circuito para IonQ + simulación exacta/Trotter/ruido
    POST /api/ionq/submit                envía el circuito a IonQ (simulador o QPU)
    GET  /api/ionq/jobs                  trabajos registrados localmente
    GET  /api/ionq/jobs/{job_id}         estado / resultado (consulta IonQ si hay clave)
    GET  /                               frontend (frontend/index.html)
"""

from __future__ import annotations

import json
import threading
import traceback
from collections import OrderedDict
from contextlib import asynccontextmanager

import numpy as np
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .. import __version__, config
from ..connectome import get_connectome
from ..ionq import IonQClient, IonQError
from ..ionq import experiment
from ..microcircuits import MICROCIRCUITS
from ..pipeline import full_network_walk, simulate_microcircuit
from .schemas import IonQSubmitRequest, MicrocircuitRequest, WalkRequest


class _LRU:
    """Caché LRU de respuestas ya serializadas (mismo pedido → misma respuesta, sin recalcular)."""

    def __init__(self, size: int = 64):
        self.size, self.data, self.lock = size, OrderedDict(), threading.Lock()

    def get(self, key):
        with self.lock:
            if key in self.data:
                self.data.move_to_end(key)
                return self.data[key]
        return None

    def put(self, key, value):
        with self.lock:
            self.data[key] = value
            self.data.move_to_end(key)
            while len(self.data) > self.size:
                self.data.popitem(last=False)


_CACHE = _LRU(96)


async def _cached(kind: str, req, compute) -> Response:
    key = kind + json.dumps(req.model_dump(), sort_keys=True)
    body = _CACHE.get(key)
    if body is None:
        body = _json(await run_in_threadpool(compute)).body
        _CACHE.put(key, body)
    return Response(body, media_type="application/json")


def _json(data, status: int = 200) -> JSONResponse:
    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, np.ndarray):
            return clean(o.tolist())
        if isinstance(o, float) and (np.isnan(o) or np.isinf(o)):
            return None
        return o

    return JSONResponse(clean(data), status_code=status)


async def _body(request: Request, model):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return model.model_validate(payload or {})


def handle_errors(fn):
    async def wrapper(request: Request):
        try:
            return await fn(request)
        except ValidationError as exc:
            return _json({"error": "Parámetros inválidos", "detail": exc.errors(include_url=False)}, 422)
        except (KeyError, ValueError, FileNotFoundError) as exc:
            return _json({"error": str(exc).strip("'\"")}, 400)
        except IonQError as exc:
            return _json({"error": str(exc)}, 502)
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            return _json({"error": f"Error interno: {exc}"}, 500)

    return wrapper


# ---------------------------------------------------------------------------
@handle_errors
async def health(request: Request):
    return _json({
        "status": "ok",
        "version": __version__,
        "ionq_configured": bool(config.IONQ_API_KEY),
        "allow_qpu": config.ALLOW_QPU,
        "default_noise_model": config.DEFAULT_NOISE_MODEL,
    })


@handle_errors
async def connectome(request: Request):
    weighting = request.query_params.get("weighting", "log")
    C = get_connectome(weighting)  # type: ignore[arg-type]
    degree = (C.J > 0).sum(axis=1)
    strength = C.J.sum(axis=1)
    neurons = [
        {"name": nm, "x": float(p[0]), "y": float(p[1]), "z": float(p[2]), "type": tp,
         "neurotransmitters": nt, "degree": int(d), "strength": round(float(s), 5)}
        for nm, p, tp, nt, d, s in zip(C.names, C.positions, C.types, C.neurotransmitters, degree, strength)
    ]
    max_edges = int(request.query_params.get("max_edges", 1500))
    edges = sorted(C.edge_list(), key=lambda e: -e[2])[:max_edges]
    return _json({
        "neurons": neurons,
        "edges": [[i, j, round(w, 5)] for i, j, w in edges],
        "n_edges_total": len(C.edge_list()),
        "weighting": C.weighting,
        "spectral_scale": C.scale,
        "source": "Cook et al. 2019 (Nature) vía OpenWorm c302 · posiciones: OpenWorm CElegansNeuroML",
    })


@handle_errors
async def walk(request: Request):
    req = await _body(request, WalkRequest)
    return await _cached("walk", req, lambda: full_network_walk(
        req.source, req.theta, req.gamma, req.t_max, req.frames, req.weighting))


@handle_errors
async def microcircuits(request: Request):
    C = get_connectome()
    out = []
    for m in MICROCIRCUITS.values():
        J = C.sub_coupling(list(m.neurons))
        out.append({**m.to_dict(), "n_edges": int((np.triu(J, 1) > 0).sum())})
    return _json({"microcircuits": out})


@handle_errors
async def micro_simulate(request: Request):
    req = await _body(request, MicrocircuitRequest)
    return await _cached("micro", req, lambda: simulate_microcircuit(**req.model_dump()))


@handle_errors
async def ionq_submit(request: Request):
    req = await _body(request, IonQSubmitRequest)
    client = IonQClient()
    p = req.model_dump()
    record = await run_in_threadpool(
        experiment.submit_microcircuit,
        client, backend=p["backend"], noise_model=p["noise_model"], shots=p["shots"], gateset=p["gateset"],
        preset=p["preset"], neurons=p["neurons"], sources=p["sources"], theta=p["theta"], t=p["t"],
        gamma=p["gamma"], mode=p["mode"], steps=p["steps"], order=p["order"],
    )
    return _json({k: record[k] for k in ("job_id", "backend", "status", "params", "gate_counts")})


@handle_errors
async def ionq_jobs(request: Request):
    return _json({"jobs": experiment.list_records()})


@handle_errors
async def ionq_job(request: Request):
    job_id = request.path_params["job_id"]
    if config.IONQ_API_KEY:
        record = await run_in_threadpool(experiment.refresh_record, IonQClient(), job_id)
    else:
        record = experiment.load_record(job_id)
    record.pop("request", None)
    return _json(record)


def create_app() -> Starlette:
    routes = [
        Route("/api/health", health),
        Route("/api/connectome", connectome),
        Route("/api/walk", walk, methods=["POST"]),
        Route("/api/microcircuits", microcircuits),
        Route("/api/microcircuit/simulate", micro_simulate, methods=["POST"]),
        Route("/api/ionq/submit", ionq_submit, methods=["POST"]),
        Route("/api/ionq/jobs", ionq_jobs),
        Route("/api/ionq/jobs/{job_id}", ionq_job),
    ]
    if config.FRONTEND_DIR.exists():
        routes.append(Mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend"))
    middleware = [
        Middleware(GZipMiddleware, minimum_size=1000),
        Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
    ]
    return Starlette(routes=routes, middleware=middleware, lifespan=_lifespan)


@asynccontextmanager
async def _lifespan(app):
    _warm_up()
    yield


def _warm_up() -> None:
    """Precalcula en segundo plano lo que la interfaz pide al abrirse (primer uso más rápido)."""
    def work():
        try:
            get_connectome().eigh()
            full_network_walk("AVM")
        except Exception:  # pragma: no cover
            traceback.print_exc()
    threading.Thread(target=work, daemon=True).start()


app = create_app()
