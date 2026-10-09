"""Configuración central (rutas y variables de entorno)."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
RESULTS_DIR = DATA_DIR / "results"
FRONTEND_DIR = PROJECT_DIR / "frontend"


def _load_dotenv(path: Path) -> None:
    """Carga un .env simple (CLAVE=valor) sin dependencias externas."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BACKEND_DIR / ".env")

# --- IonQ -----------------------------------------------------------------
IONQ_API_KEY: str | None = os.environ.get("IONQ_API_KEY") or None
IONQ_API_URL: str = os.environ.get("IONQ_API_URL", "https://api.ionq.co/v0.4")
# Las corridas en QPU cuestan dinero: hay que habilitarlas explícitamente.
ALLOW_QPU: bool = os.environ.get("ALLOW_QPU", "false").lower() in {"1", "true", "yes"}
DEFAULT_NOISE_MODEL: str = os.environ.get("IONQ_NOISE_MODEL", "forte-1")

# Fidelidades de referencia de IonQ Forte (ionq.com/quantum-systems/compare).
FORTE_F1Q: float = 0.9998
FORTE_F2Q: float = 0.996
FORTE_READOUT_ERROR: float = 0.005  # supuesto conservador para el simulador local

# --- Servidor ---------------------------------------------------------------
HOST: str = os.environ.get("HOST", "127.0.0.1")
PORT: int = int(os.environ.get("PORT", "8000"))
