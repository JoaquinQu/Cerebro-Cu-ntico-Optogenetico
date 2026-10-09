"""Conectoma de C. elegans → matriz de acoplamientos J (hermítica).

Datos (ver docs/TEORIA.md §2):
    * neurons.json            302 neuronas, posición del soma (OpenWorm, CElegansNeuroML)
                              y tipo (sensorial / interneurona / motora).
    * connectome_cook2019.csv sinapsis químicas y uniones gap del hermafrodita
                              (Cook et al., Nature 2019), vía OpenWorm c302.

Construcción:
    W_ij = f(químicas i→j) + f(químicas j→i) simetrizado + f(gap i–j)
    J    = W / λ_max(W)          (normalización espectral: ‖J‖ = 1)

La simetrización es necesaria porque un hamiltoniano debe ser hermítico; la
direccionalidad de la sinapsis química se pierde (limitación discutida en la teoría).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Literal

import numpy as np

from .config import DATA_DIR

Weighting = Literal["binary", "count", "log"]
TYPE_ORDER = ("sensory", "interneuron", "motor", "unknown")


def _weight(count: float, weighting: Weighting) -> float:
    if weighting == "binary":
        return 1.0
    if weighting == "count":
        return float(count)
    if weighting == "log":
        return float(np.log1p(count))
    raise ValueError(f"weighting desconocido: {weighting}")


@dataclass
class Connectome:
    """Grafo neuronal listo para física cuántica."""

    names: list[str]
    positions: np.ndarray  # (N, 3) en micrómetros
    types: list[str]
    neurotransmitters: list[list[str]]
    W: np.ndarray  # pesos simétricos sin normalizar
    J: np.ndarray  # pesos normalizados, ‖J‖₂ = 1
    scale: float  # λ_max(W)
    weighting: str
    edges_raw: list[tuple[str, str, int, str]] = field(repr=False, default_factory=list)

    # -- utilidades ---------------------------------------------------------
    @property
    def n(self) -> int:
        return len(self.names)

    def index(self, name: str) -> int:
        try:
            return self._index[name]
        except AttributeError:
            self._index = {nm: i for i, nm in enumerate(self.names)}
            return self._index[name]
        except KeyError as exc:  # pragma: no cover - mensaje claro
            raise KeyError(f"Neurona desconocida: {name}") from exc

    def indices(self, names: Iterable[str]) -> list[int]:
        return [self.index(nm) for nm in names]

    def sub_coupling(self, names: list[str]) -> np.ndarray:
        """J restringido a un subconjunto (misma escala global que la red completa)."""
        idx = self.indices(names)
        return self.J[np.ix_(idx, idx)].copy()

    def edge_list(self, min_weight: float = 0.0) -> list[tuple[int, int, float]]:
        """Aristas (i<j, J_ij) con J_ij > min_weight."""
        iu, ju = np.triu_indices(self.n, k=1)
        w = self.J[iu, ju]
        keep = w > min_weight
        return [(int(i), int(j), float(x)) for i, j, x in zip(iu[keep], ju[keep], w[keep])]

    @lru_cache(maxsize=4)
    def eigh(self) -> tuple[np.ndarray, np.ndarray]:
        """Diagonalización de J (se calcula una vez; J es real simétrica)."""
        return np.linalg.eigh(self.J)

    def __hash__(self) -> int:  # necesario para lru_cache en el método
        return id(self)


def load_neurons() -> list[dict]:
    return json.loads((DATA_DIR / "neurons.json").read_text(encoding="utf-8"))


def load_edges() -> list[tuple[str, str, int, str]]:
    rows = []
    with open(DATA_DIR / "connectome_cook2019.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append((r["source"], r["target"], int(r["weight"]), r["type"]))
    return rows


def build_connectome(
    weighting: Weighting = "log",
    include: tuple[str, ...] = ("chemical", "electrical"),
) -> Connectome:
    neurons = load_neurons()
    names = [d["name"] for d in neurons]
    idx = {nm: i for i, nm in enumerate(names)}
    n = len(names)

    chem = np.zeros((n, n))
    gap = np.zeros((n, n))
    edges = load_edges()
    for a, b, count, kind in edges:
        if kind not in include:
            continue
        i, j = idx[a], idx[b]
        if kind == "chemical":
            chem[i, j] += count
        else:
            gap[i, j] += count

    # Simetrización: química en ambos sentidos se suma; gap se promedia (ya es simétrica
    # en el dato, pero algunas entradas aparecen en un solo sentido).
    chem_sym = chem + chem.T
    gap_sym = np.maximum(gap, gap.T)
    counts = chem_sym + gap_sym
    W = np.zeros_like(counts)
    nz = counts > 0
    W[nz] = np.vectorize(lambda c: _weight(c, weighting))(counts[nz])
    np.fill_diagonal(W, 0.0)

    scale = float(np.max(np.abs(np.linalg.eigvalsh(W))))
    J = W / scale

    positions = np.array([[d["x"], d["y"], d["z"]] for d in neurons], dtype=float)
    types = [next((t for t in TYPE_ORDER if t in d["types"]), "unknown") for d in neurons]
    return Connectome(
        names=names,
        positions=positions,
        types=types,
        neurotransmitters=[d.get("neurotransmitters", []) for d in neurons],
        W=W,
        J=J,
        scale=scale,
        weighting=weighting,
        edges_raw=edges,
    )


@lru_cache(maxsize=3)
def get_connectome(weighting: Weighting = "log") -> Connectome:
    """Conectoma cacheado (se construye una vez por tipo de peso)."""
    return build_connectome(weighting=weighting)
