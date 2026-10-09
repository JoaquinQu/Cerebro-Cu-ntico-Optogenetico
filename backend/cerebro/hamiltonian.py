"""Dinámica exacta: modelo XY en el grafo ≡ quantum walk de tiempo continuo.

Hamiltoniano (docs/TEORIA.md §3):

    H = γ Σ_{i<j} J_ij (X_i X_j + Y_i Y_j)/2  =  γ Σ_{i<j} J_ij (σ⁺_i σ⁻_j + σ⁻_i σ⁺_j)

* Conserva el número de excitaciones  N̂ = Σ_k |1⟩⟨1|_k.
* En el sector de una excitación  {|e_k⟩}  actúa como  γ J  ⇒  quantum walk.
* El vacío |0…0⟩ es autoestado con energía 0.

Por eso el pulso láser  RX(θ)  en la neurona j produce

    P_k(t) = sin²(θ/2) · |⟨k| e^{-iγJt} |j⟩|²

que se calcula exactamente para las 302 neuronas diagonalizando J una sola vez.
Convención de qubits: el qubit q es el bit q del índice de la base (q0 = bit menos
significativo), igual que IonQ y Qiskit.
"""

from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import expm_multiply


# ---------------------------------------------------------------------------
# Sector de una excitación (red completa, 302 neuronas)
# ---------------------------------------------------------------------------
def walk_amplitudes(
    eig: tuple[np.ndarray, np.ndarray], source: int, times: np.ndarray, gamma: float = 1.0
) -> np.ndarray:
    """Amplitudes ⟨k|e^{-iγJt}|source⟩ para todos los k y tiempos. Forma (T, N)."""
    lam, V = eig
    times = np.atleast_1d(np.asarray(times, dtype=float))
    coeff = V[source, :]  # ⟨source|v_m⟩ (V real ortogonal)
    phases = np.exp(-1j * gamma * np.outer(times, lam))  # (T, M)
    return (phases * coeff) @ V.T  # (T, N)


def firing_probabilities(
    eig: tuple[np.ndarray, np.ndarray],
    source: int,
    times: np.ndarray,
    theta: float = np.pi,
    gamma: float = 1.0,
) -> np.ndarray:
    """P_k(t) = sin²(θ/2)|⟨k|e^{-iγJt}|source⟩|². Forma (T, N)."""
    amp = walk_amplitudes(eig, source, times, gamma)
    return np.sin(theta / 2) ** 2 * np.abs(amp) ** 2


def arrival_times(probs: np.ndarray, times: np.ndarray, threshold: float = 0.02) -> np.ndarray:
    """Primer tiempo en que P_k supera el umbral (nan si nunca)."""
    hit = probs >= threshold
    first = np.where(hit.any(axis=0), hit.argmax(axis=0), -1)
    out = np.full(probs.shape[1], np.nan)
    ok = first >= 0
    out[ok] = np.asarray(times)[first[ok]]
    return out


def classical_diffusion(J: np.ndarray, source: int, times: np.ndarray) -> np.ndarray:
    """Referencia clásica (no usada en la demo): p(t)=e^{-Lt} e_j con L = I - D^{-1/2} J D^{-1/2}."""
    d = J.sum(axis=1)
    d[d == 0] = 1.0
    Dm = 1.0 / np.sqrt(d)
    L = np.eye(len(J)) - (Dm[:, None] * J * Dm[None, :])
    lam, V = np.linalg.eigh(L)
    out = []
    for t in np.atleast_1d(times):
        y = V @ (np.exp(-lam * t) * V[source] / Dm[source])
        out.append(np.clip(y * Dm, 0, None))
    return np.array(out)


# ---------------------------------------------------------------------------
# Espacio de Hilbert completo (microcircuitos, n ≤ ~16 qubits)
# ---------------------------------------------------------------------------
def xy_hamiltonian(J: np.ndarray, gamma: float = 1.0) -> sparse.csr_matrix:
    """H = γ Σ_{i<j} J_ij (σ⁺_iσ⁻_j + h.c.) como matriz dispersa 2^n × 2^n."""
    n = len(J)
    dim = 1 << n
    basis = np.arange(dim)
    rows, cols, vals = [], [], []
    for i in range(n):
        for j in range(i + 1, n):
            w = J[i, j]
            if w == 0:
                continue
            bi = (basis >> i) & 1
            bj = (basis >> j) & 1
            mask = bi != bj  # σ⁺σ⁻ sólo conecta |01⟩ ↔ |10⟩ en (i, j)
            src = basis[mask]
            dst = src ^ ((1 << i) | (1 << j))
            rows.append(dst)
            cols.append(src)
            vals.append(np.full(src.size, gamma * w))
    if not rows:
        return sparse.csr_matrix((dim, dim), dtype=complex)
    return sparse.csr_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(dim, dim),
        dtype=complex,
    )


def laser_state(n: int, sources: list[int], theta: float) -> np.ndarray:
    """⊗_s RX(θ)_s |0…0⟩ — el pulso optogenético sobre las neuronas fuente."""
    c, s = np.cos(theta / 2), -1j * np.sin(theta / 2)
    psi = np.zeros(1 << n, dtype=complex)
    psi[0] = 1.0
    for q in sources:
        new = np.zeros_like(psi)
        idx = np.arange(1 << n)
        zero = ((idx >> q) & 1) == 0
        new[idx[zero]] += c * psi[idx[zero]]
        new[idx[zero] | (1 << q)] += s * psi[idx[zero]]
        new[idx[~zero]] += c * psi[idx[~zero]]
        new[idx[~zero] ^ (1 << q)] += s * psi[idx[~zero]]
        psi = new
    return psi


def evolve_exact(J: np.ndarray, sources: list[int], theta: float, t: float, gamma: float = 1.0) -> np.ndarray:
    """Estado exacto e^{-iHt} ⊗RX(θ)|0⟩ en el espacio completo (2^n)."""
    psi0 = laser_state(len(J), sources, theta)
    if t == 0:
        return psi0
    return expm_multiply(-1j * t * xy_hamiltonian(J, gamma), psi0)


def marginals(probs: np.ndarray, n: int) -> np.ndarray:
    """P(qubit k = 1) a partir de la distribución sobre 2^n estados."""
    idx = np.arange(1 << n)
    return np.array([probs[((idx >> k) & 1) == 1].sum() for k in range(n)])
