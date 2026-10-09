"""Post-selección por simetría y métricas (TEORIA §5 y §8).

El hamiltoniano XY conserva el número de excitaciones: con k láseres ningún disparo
ideal tiene más de k bits en 1. Los que sí los tienen son errores y se descartan.
"""

from __future__ import annotations

import numpy as np


def peso_hamming(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.int64)
    c = np.zeros_like(x)
    while np.any(x):
        c += x & 1
        x >>= 1
    return c


def conteos_a_probs(conteos: dict, n: int) -> np.ndarray:
    """Conteos de Qiskit ('0101': 37, …; el qubit 0 es el carácter de la derecha) → vector 2^n."""
    p = np.zeros(1 << n)
    for clave, v in conteos.items():
        p[int(str(clave).replace(" ", ""), 2)] += float(v)
    s = p.sum()
    return p / s if s else p


def postseleccionar(probs: np.ndarray, n: int, k: int) -> tuple[np.ndarray, float]:
    ok = peso_hamming(np.arange(1 << n)) <= k
    aceptado = float(probs[ok].sum())
    out = np.where(ok, probs, 0.0)
    return (out / aceptado if aceptado > 0 else out), aceptado


def marginales(probs: np.ndarray, n: int) -> list[float]:
    idx = np.arange(1 << n)
    return [float(probs[((idx >> q) & 1) == 1].sum()) for q in range(n)]


def tvd(p, q) -> float:
    return 0.5 * float(np.abs(np.asarray(p) - np.asarray(q)).sum())


def comparar(exacta: np.ndarray, medida: np.ndarray, n: int, k: int) -> dict:
    ps, aceptado = postseleccionar(medida, n, k)
    return {
        "tvd_bruto": tvd(exacta, medida),
        "tvd_postseleccion": tvd(exacta, ps),
        "fraccion_aceptada": aceptado,
        "marginales_bruto": marginales(medida, n),
        "marginales_postseleccion": marginales(ps, n),
    }
