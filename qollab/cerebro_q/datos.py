"""Datos del conectoma de C. elegans.

Las rutas están escritas como texto literal porque el runtime de Qollab sólo carga
los archivos del proyecto cuyas rutas aparecen así en el código.
"""

from __future__ import annotations

import base64
import csv
import json
import re
from functools import lru_cache

import numpy as np

RUTA_NEURONAS = "data/neurons.json"
RUTA_SINAPSIS = "data/connectome_cook2019.csv"
RUTA_CUERPO = "data/gusano.glb"
TIPOS = ("sensory", "interneuron", "motor", "unknown")


@lru_cache(maxsize=1)
def neuronas() -> list[dict]:
    with open(RUTA_NEURONAS, encoding="utf-8") as fh:
        datos = json.load(fh)
    for d in datos:
        d["type"] = next((t for t in TIPOS if t in d.get("types", [])), "unknown")
    return datos


@lru_cache(maxsize=1)
def sinapsis() -> list[tuple[str, str, int, str]]:
    filas = []
    with open(RUTA_SINAPSIS, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            filas.append((r["source"], r["target"], int(r["weight"]), r["type"]))
    return filas


@lru_cache(maxsize=1)
def cuerpo_glb_base64() -> str:
    """El modelo 3D del cuerpo (JS no puede leer archivos del proyecto: se lo pasa Python)."""
    with open(RUTA_CUERPO, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def normalizar_nombre(nombre: str) -> str:
    return re.sub(r"^([A-Z]+)0(\d)$", r"\1\2", nombre.strip().upper())


def posiciones() -> np.ndarray:
    return np.array([[d["x"], d["y"], d["z"]] for d in neuronas()], dtype=float)
