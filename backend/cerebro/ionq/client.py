"""Cliente mínimo de la API REST de IonQ v0.4 (sin depender de qiskit-ionq).

Documentación usada (oct. 2026):
    POST {base}/jobs                         crea un trabajo  (type "ionq.circuit.v1")
    GET  {base}/jobs/{id}                    estado: submitted|ready|started|completed|failed|canceled
    GET  {base}/jobs/{id}/results/probabilities   {"<entero>": prob, ...}
    Autenticación: header  "Authorization: apiKey <clave>"
    Backends:  "simulator" (con "noise": {"model": "forte-1"|"aria-1"|"ideal"...}),
               "qpu.forte-1", "qpu.forte-enterprise-1"

Orden de bits: las claves del resultado son el entero cuya representación binaria
tiene el qubit 0 como bit menos significativo. `scripts/run_ionq_experiment.py`
lo verifica antes de cada experimento con un circuito de calibración (X en q0).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from .. import config


class IonQError(RuntimeError):
    pass


QPU_BACKENDS = {"qpu.forte-1", "qpu.forte-enterprise-1", "qpu.aria-1", "qpu.aria-2"}


@dataclass
class IonQClient:
    api_key: str | None = None
    base_url: str = config.IONQ_API_URL
    timeout: float = 30.0

    def __post_init__(self) -> None:
        self.api_key = self.api_key or config.IONQ_API_KEY
        if not self.api_key:
            raise IonQError("Falta IONQ_API_KEY (ponla en backend/.env o como variable de entorno).")

    # -- HTTP ---------------------------------------------------------------
    @property
    def _headers(self) -> dict:
        return {"Authorization": f"apiKey {self.api_key}", "Content-Type": "application/json"}

    def _request(self, method: str, path: str, **kw) -> dict:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        resp = requests.request(method, url, headers=self._headers, timeout=self.timeout, **kw)
        if resp.status_code >= 400:
            raise IonQError(f"IonQ {resp.status_code} en {method} {path}: {resp.text[:500]}")
        return resp.json() if resp.content else {}

    # -- trabajos -------------------------------------------------------------
    @staticmethod
    def build_job(
        circuit_input: dict,
        backend: str = "simulator",
        shots: int = 1000,
        noise_model: str | None = None,
        name: str = "cerebro-cuantico",
        metadata: dict | None = None,
    ) -> dict:
        body = {
            "type": "ionq.circuit.v1",
            "name": name,
            "shots": int(shots),
            "backend": backend,
            "input": circuit_input,
        }
        if backend == "simulator" and noise_model:
            body["noise"] = {"model": noise_model}
        if metadata:
            # IonQ acepta metadatos como strings cortos
            body["metadata"] = {str(k): str(v)[:400] for k, v in metadata.items()}
        return body

    def submit(self, job: dict) -> str:
        if job.get("backend") in QPU_BACKENDS and not config.ALLOW_QPU:
            raise IonQError(
                "Envío a QPU bloqueado: define ALLOW_QPU=true en backend/.env cuando estés seguro "
                "(las corridas en hardware tienen costo)."
            )
        data = self._request("POST", "/jobs", json=job)
        return data["id"]

    def get_job(self, job_id: str) -> dict:
        return self._request("GET", f"/jobs/{job_id}")

    def get_probabilities(self, job_id: str) -> dict[int, float]:
        raw = self._request("GET", f"/jobs/{job_id}/results/probabilities")
        return {int(k): float(v) for k, v in raw.items()}

    def wait(self, job_id: str, timeout_s: float = 3600, poll_s: float = 5.0) -> dict:
        t0 = time.time()
        while True:
            job = self.get_job(job_id)
            status = job.get("status")
            if status == "completed":
                return job
            if status in {"failed", "canceled"}:
                raise IonQError(f"Trabajo {job_id} terminó con estado {status}: {job.get('failure')}")
            if time.time() - t0 > timeout_s:
                raise IonQError(f"Tiempo de espera agotado para {job_id} (estado {status})")
            time.sleep(poll_s)
