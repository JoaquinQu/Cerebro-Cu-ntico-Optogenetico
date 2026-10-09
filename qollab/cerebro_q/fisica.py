"""Física exacta (docs/TEORIA.md §2–§4).

    J = W / λ_max(W),   W_ij = 1 si hay al menos una sinapsis (química en cualquier sentido o gap), 0 si no
    (pesos binarios: decisión del equipo; todas las conexiones pesan lo mismo)
    H = γ Σ_{i<j} J_ij (X_i X_j + Y_i Y_j)/2        (modelo XY)
    Sector de una excitación:  H = γ J   ⇒  quantum walk
    Láser RX(θ) en la neurona j:  P_k(t) = sin²(θ/2) |[e^{-iγJt}]_kj|²
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from . import datos


@lru_cache(maxsize=1)
def acoplamientos() -> tuple[np.ndarray, list[str], float]:
    """(J normalizada, nombres, λ_max(W))."""
    neu = datos.neuronas()
    nombres = [d["name"] for d in neu]
    idx = {n: i for i, n in enumerate(nombres)}
    n = len(nombres)
    quim = np.zeros((n, n))
    gap = np.zeros((n, n))
    for a, b, w, tipo in datos.sinapsis():
        if a in idx and b in idx and a != b:
            (quim if tipo == "chemical" else gap)[idx[a], idx[b]] += w
    conteo = quim + quim.T + np.maximum(gap, gap.T)
    W = (conteo > 0).astype(float)  # binario: todas las sinapsis pesan igual
    np.fill_diagonal(W, 0.0)
    escala = float(np.max(np.abs(np.linalg.eigvalsh(W))))
    return W / escala, nombres, escala


@lru_cache(maxsize=1)
def diagonalizacion() -> tuple[np.ndarray, np.ndarray]:
    J, _, _ = acoplamientos()
    return np.linalg.eigh(J)


def indice(nombre: str) -> int:
    _, nombres, _ = acoplamientos()
    nombre = datos.normalizar_nombre(nombre)
    if nombre not in nombres:
        raise ValueError(f"Neurona desconocida: {nombre}")
    return nombres.index(nombre)


def probabilidades_walk(eig, fuente: int, tiempos: np.ndarray, theta: float, gamma: float) -> np.ndarray:
    """P_k(t) para todas las neuronas. Forma (T, N)."""
    lam, V = eig
    fases = np.exp(-1j * gamma * np.outer(tiempos, lam))
    amp = (fases * V[fuente, :]) @ V.T
    return np.sin(theta / 2) ** 2 * np.abs(amp) ** 2


def sub_acoplamientos(nombres_sub: list[str]) -> np.ndarray:
    J, _, _ = acoplamientos()
    idx = [indice(n) for n in nombres_sub]
    return J[np.ix_(idx, idx)].copy()


def distribucion_exacta(J: np.ndarray, fuentes: list[int], theta: float, t: float, gamma: float) -> np.ndarray:
    """Distribución exacta sobre 2^n estados del microcircuito (espacio de Hilbert completo)."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.linalg import expm_multiply

    n = len(J)
    dim = 1 << n
    base = np.arange(dim)
    filas, cols, vals = [], [], []
    for i in range(n):
        for j in range(i + 1, n):
            if J[i, j] == 0:
                continue
            distinto = ((base >> i) & 1) != ((base >> j) & 1)
            src = base[distinto]
            filas.append(src ^ ((1 << i) | (1 << j)))
            cols.append(src)
            vals.append(np.full(src.size, gamma * J[i, j]))
    psi = estado_laser(n, fuentes, theta)
    if t == 0 or not filas:
        return np.abs(psi) ** 2
    H = csr_matrix((np.concatenate(vals), (np.concatenate(filas), np.concatenate(cols))), shape=(dim, dim))
    return np.abs(expm_multiply(-1j * t * H, psi)) ** 2


def estado_laser(n: int, fuentes: list[int], theta: float) -> np.ndarray:
    c, s = np.cos(theta / 2), -1j * np.sin(theta / 2)
    psi = np.zeros(1 << n, dtype=complex)
    psi[0] = 1.0
    for q in fuentes:
        nuevo = np.zeros_like(psi)
        idx = np.arange(1 << n)
        cero = ((idx >> q) & 1) == 0
        nuevo[idx[cero]] += c * psi[idx[cero]]
        nuevo[idx[cero] | (1 << q)] += s * psi[idx[cero]]
        nuevo[idx[~cero]] += c * psi[idx[~cero]]
        nuevo[idx[~cero] ^ (1 << q)] += s * psi[idx[~cero]]
        psi = nuevo
    return psi


def marginales(probs: np.ndarray, n: int) -> np.ndarray:
    idx = np.arange(1 << n)
    return np.array([probs[((idx >> k) & 1) == 1].sum() for k in range(n)])
