"""Servidor falso de la API de IonQ v0.4 para probar el flujo completo sin costo.

Interpreta el JSON `ionq.circuit.v1` con un parser independiente (native y qis),
simula el circuito y responde con claves enteras little-endian (q0 = bit menos
significativo). No reemplaza la validación del servidor real de IonQ.
"""

from __future__ import annotations

import socket
import threading
import time
import uuid

import numpy as np
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from cerebro.circuits.ir import Circuit
from cerebro.circuits.simulator import probabilities

JOBS: dict[str, dict] = {}


def parse_input(inp: dict) -> Circuit:
    c = Circuit(int(inp["qubits"]))
    for op in inp["circuit"]:
        g = op["gate"]
        if g in ("gpi", "gpi2"):
            c.add(g, [op["target"]], [op["phase"]])
        elif g == "zz":
            c.add("zz", op["targets"], [op["angle"]])
        elif g == "ms":
            c.add("ms", op["targets"], [*op["phases"], op.get("angle", 0.25)])
        elif g == "cnot":
            c.add("cnot", [op["control"], op["target"]])
        elif g in ("rx", "ry", "rz"):
            c.add(g, [op["target"]], [op["rotation"]])
        elif g in ("h", "x"):
            c.add(g, [op["target"]])
        else:
            raise ValueError(g)
    return c


async def create(request: Request):
    if request.headers.get("authorization", "") != "apiKey test-key":
        return JSONResponse({"error": "unauthorized"}, 401)
    body = await request.json()
    assert body["type"] == "ionq.circuit.v1"
    gs = body["input"]["gateset"]
    allowed = {"native": {"gpi", "gpi2", "zz", "ms"}, "qis": {"h", "x", "rx", "ry", "rz", "cnot"}}[gs]
    if not {op["gate"] for op in body["input"]["circuit"]} <= allowed:
        return JSONResponse({"error": "mixed gatesets"}, 400)
    jid = str(uuid.uuid4())
    p = probabilities(parse_input(body["input"]))
    JOBS[jid] = {"id": jid, "status": "completed", "backend": body["backend"],
                 "probs": {str(i): float(v) for i, v in enumerate(p) if v > 1e-12},
                 "stats": {"qubits": body["input"]["qubits"]}}
    return JSONResponse({"id": jid, "status": "submitted"}, 201)


async def get_job(request: Request):
    j = JOBS[request.path_params["jid"]]
    return JSONResponse({k: v for k, v in j.items() if k != "probs"})


async def get_probs(request: Request):
    return JSONResponse(JOBS[request.path_params["jid"]]["probs"])


app = Starlette(routes=[
    Route("/v0.4/jobs", create, methods=["POST"]),
    Route("/v0.4/jobs/{jid}", get_job),
    Route("/v0.4/jobs/{jid}/results/probabilities", get_probs),
])


def start() -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    return f"http://127.0.0.1:{port}/v0.4"
