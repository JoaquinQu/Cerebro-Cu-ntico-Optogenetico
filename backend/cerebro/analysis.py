"""Post-selección por simetría y métricas de comparación (docs/TEORIA.md §8).

El hamiltoniano XY conserva el número de excitaciones. Con k láseres, ningún
resultado ideal puede tener más de k "spikes" (bits en 1). Los disparos que violan
esta ley son errores del hardware y se descartan (symmetry verification:
Bonet-Monroig et al. 2018; McArdle et al. 2019).
"""

from __future__ import annotations

import numpy as np


def popcount(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.int64)
    c = np.zeros_like(x)
    while np.any(x):
        c += x & 1
        x = x >> 1
    return c


def counts_to_probs(counts: dict[int, float], n: int) -> np.ndarray:
    p = np.zeros(1 << n)
    for k, v in counts.items():
        p[int(k)] += float(v)
    s = p.sum()
    return p / s if s > 0 else p


def postselect(probs: np.ndarray, n: int, max_excitations: int) -> tuple[np.ndarray, float]:
    """Anula los estados con más de `max_excitations` bits en 1 y renormaliza.

    Devuelve (distribución post-seleccionada, fracción de disparos aceptados).
    """
    w = popcount(np.arange(1 << n))
    keep = w <= max_excitations
    accepted = float(probs[keep].sum())
    out = np.where(keep, probs, 0.0)
    return (out / accepted if accepted > 0 else out), accepted


def neuron_marginals(probs: np.ndarray, n: int) -> np.ndarray:
    idx = np.arange(1 << n)
    return np.array([probs[((idx >> k) & 1) == 1].sum() for k in range(n)])


def tvd(p: np.ndarray, q: np.ndarray) -> float:
    """Distancia de variación total ½Σ|p−q| ∈ [0, 1]."""
    return 0.5 * float(np.abs(np.asarray(p) - np.asarray(q)).sum())


def hellinger_fidelity(p: np.ndarray, q: np.ndarray) -> float:
    """(Σ√(p q))² ∈ [0, 1]  (1 = distribuciones idénticas)."""
    return float(np.sum(np.sqrt(np.clip(p, 0, None) * np.clip(q, 0, None))) ** 2)


def summarize(ideal: np.ndarray, measured: np.ndarray, n: int, n_sources: int) -> dict:
    """Comparación completa ideal vs. medido, con y sin post-selección."""
    ps, acc = postselect(measured, n, n_sources)
    return {
        "tvd_raw": tvd(ideal, measured),
        "tvd_postselected": tvd(ideal, ps),
        "fidelity_raw": hellinger_fidelity(ideal, measured),
        "fidelity_postselected": hellinger_fidelity(ideal, ps),
        "accepted_fraction": acc,
        "marginals_ideal": neuron_marginals(ideal, n).tolist(),
        "marginals_raw": neuron_marginals(measured, n).tolist(),
        "marginals_postselected": neuron_marginals(ps, n).tolist(),
    }
