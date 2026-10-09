"""Flujo de experimentos en IonQ con registro local reproducible.

Cada trabajo enviado queda guardado en  backend/data/results/jobs/<id>.json  con:
    * parámetros físicos (neuronas, láser θ, tiempo t, γ, modo, pasos de Trotter)
    * el circuito exacto que se envió (bloque `input` de la API)
    * la distribución ideal (para comparar) y, al completarse, la medida y su análisis
Así el frontend puede mostrar resultados de hardware sin volver a pagar por ellos.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from .. import config
from ..analysis import summarize
from ..circuits import compile_native, lower_to_qis, to_ionq_input
from ..circuits.ir import Circuit
from ..hamiltonian import evolve_exact
from ..pipeline import resolve_neurons
from ..connectome import get_connectome
from ..circuits.builders import build_microcircuit
from .client import IonQClient

JOBS_DIR = config.RESULTS_DIR / "jobs"


def _save(record: dict) -> Path:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    path = JOBS_DIR / f"{record['job_id']}.json"
    path.write_text(json.dumps(record, indent=1), encoding="utf-8")
    return path


def load_record(job_id: str) -> dict:
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        raise FileNotFoundError(job_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_records() -> list[dict]:
    if not JOBS_DIR.exists():
        return []
    out = []
    for p in sorted(JOBS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        r = json.loads(p.read_text(encoding="utf-8"))
        out.append({k: r.get(k) for k in ("job_id", "backend", "noise_model", "status", "submitted_at",
                                          "params", "analysis")})
    return out


# ---------------------------------------------------------------------------
def endianness_check(client: IonQClient) -> bool:
    """True si el qubit 0 es el bit menos significativo de las claves de IonQ.

    Circuito: X en q0 de un registro de 2 qubits, simulador ideal (sin costo).
    """
    circ = Circuit(2)
    circ.add("x", [0])
    job = client.build_job(to_ionq_input(compile_native(circ)), "simulator", 100, None, "endianness-check")
    jid = client.submit(job)
    client.wait(jid, timeout_s=300, poll_s=2)
    probs = client.get_probabilities(jid)
    key = max(probs, key=probs.get)
    if key == 1:
        return True
    if key == 2:
        return False
    raise RuntimeError(f"Resultado inesperado en la calibración: {probs}")


def remap(probs: dict[int, float], n: int, little_endian: bool) -> np.ndarray:
    p = np.zeros(1 << n)
    for k, v in probs.items():
        idx = k if little_endian else int(format(k, f"0{n}b")[::-1], 2)
        p[idx] += v
    return p / p.sum()


def submit_microcircuit(
    client: IonQClient,
    backend: str = "simulator",
    noise_model: str | None = config.DEFAULT_NOISE_MODEL,
    shots: int = 1000,
    gateset: str = "native",
    preset: str | None = "toque-6",
    neurons: list[str] | None = None,
    sources: list[str] | None = None,
    theta: float = float(np.pi),
    t: float = 30.0,
    gamma: float = 1.0,
    mode: str = "trotter",
    steps: int = 2,
    order: int = 2,
    little_endian: bool = True,
) -> dict:
    C = get_connectome()
    names = resolve_neurons(preset, neurons)
    J = C.sub_coupling(names)
    sources = sources or [names[0]]
    src = [names.index(s) for s in sources]
    logical = build_microcircuit(J, src, theta, t, gamma, mode, steps, order, labels=names)  # type: ignore[arg-type]
    compiled = compile_native(logical) if gateset == "native" else lower_to_qis(logical)
    circuit_input = to_ionq_input(compiled)
    job = client.build_job(circuit_input, backend, shots, noise_model if backend == "simulator" else None,
                           name=f"cerebro-{preset or 'custom'}-t{t:g}")
    jid = client.submit(job)
    exact = np.abs(evolve_exact(J, src, theta, t, gamma)) ** 2
    record = {
        "job_id": jid,
        "backend": backend,
        "noise_model": noise_model if backend == "simulator" else None,
        "shots": shots,
        "status": "submitted",
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "little_endian": little_endian,
        "params": {"neurons": names, "sources": sources, "theta": theta, "t": t, "gamma": gamma,
                   "mode": mode, "steps": steps, "order": order, "gateset": gateset, "preset": preset},
        "gate_counts": compiled.counts(),
        "request": job,
        "exact_probs": exact.tolist(),
        "analysis": None,
    }
    _save(record)
    return record


def refresh_record(client: IonQClient, job_id: str) -> dict:
    """Consulta el estado en IonQ; si terminó, descarga y analiza el resultado."""
    record = load_record(job_id)
    if record.get("status") == "completed" and record.get("analysis"):
        return record
    job = client.get_job(job_id)
    record["status"] = job.get("status", record.get("status"))
    record["ionq_stats"] = job.get("stats")
    if record["status"] == "completed":
        n = len(record["params"]["neurons"])
        probs = client.get_probabilities(job_id)
        measured = remap(probs, n, record.get("little_endian", True))
        exact = np.array(record["exact_probs"])
        record["measured_probs"] = measured.tolist()
        record["analysis"] = summarize(exact, measured, n, len(record["params"]["sources"]))
    _save(record)
    return record
