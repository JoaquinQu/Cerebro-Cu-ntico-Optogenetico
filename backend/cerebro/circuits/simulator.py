"""Simulador de vector de estado (ideal y con ruido tipo IonQ) sin dependencias externas.

Ruido (modelo simple, docs/TEORIA.md §7):
    * Tras cada compuerta de 2 qubits: canal despolarizante de 2 qubits con
      probabilidad p2 = 1 - F2Q (Forte: F2Q ≈ 0.996).
    * Tras cada compuerta física de 1 qubit: despolarizante con p1 = 1 - F1Q.
      Las RZ son virtuales y no llevan ruido.
    * Error de lectura simétrico por qubit (bit-flip clásico en el resultado).
Se simula con trayectorias de Monte Carlo (Paulis aleatorios insertados), lo que
reproduce el canal en promedio y escala a ~16 qubits sin matrices densidad. El término
sin errores se suma analíticamente y las trayectorias reutilizan los prefijos ideales.
"""

from __future__ import annotations

import numpy as np

from .ir import Circuit, I2, X, Y, Z

_PAULIS = [I2, X, Y, Z]


def apply_1q(psi: np.ndarray, n: int, U: np.ndarray, q: int) -> np.ndarray:
    """Aplica U (2×2) al qubit q. Usa una vista (A, 2, L) del vector: sin copias de ejes."""
    t = psi.reshape(-1, 2, 1 << q)
    return np.einsum("ij,ajb->aib", U, t, optimize=False).reshape(-1)


def apply_2q(psi: np.ndarray, n: int, U: np.ndarray, a: int, b: int) -> np.ndarray:
    """Aplica U (4×4, factor izquierdo = qubit a) a los qubits (a, b)."""
    hi, lo = (a, b) if a > b else (b, a)
    t = psi.reshape(1 << (n - 1 - hi), 2, 1 << (hi - 1 - lo), 2, 1 << lo)
    U4 = U.reshape(2, 2, 2, 2)  # [sal_a, sal_b, ent_a, ent_b]
    if a > b:
        out = np.einsum("xyuv,AuMvL->AxMyL", U4, t, optimize=False)
    else:
        out = np.einsum("xyuv,AvMuL->AyMxL", U4, t, optimize=False)
    return out.reshape(-1)


def apply_gate(psi: np.ndarray, n: int, gate, U: np.ndarray | None = None) -> np.ndarray:
    U = gate.matrix if U is None else U
    if len(gate.qubits) == 1:
        return apply_1q(psi, n, U, gate.qubits[0])
    return apply_2q(psi, n, U, gate.qubits[0], gate.qubits[1])


def run_statevector(circ: Circuit, psi0: np.ndarray | None = None) -> np.ndarray:
    n = circ.n_qubits
    if psi0 is None:
        psi = np.zeros(1 << n, dtype=complex)
        psi[0] = 1.0
    else:
        psi = psi0.astype(complex).copy()
    for g, U in zip(circ.gates, _matrices(circ)):
        psi = apply_gate(psi, n, g, U)
    return psi


def circuit_unitary(circ: Circuit) -> np.ndarray:
    n = circ.n_qubits
    dim = 1 << n
    cols = []
    for k in range(dim):
        e = np.zeros(dim, dtype=complex)
        e[k] = 1
        cols.append(run_statevector(circ, e))
    return np.array(cols).T


def probabilities(circ: Circuit) -> np.ndarray:
    return np.abs(run_statevector(circ)) ** 2


def _matrices(circ: Circuit) -> list[np.ndarray]:
    return [g.matrix for g in circ.gates]


def _error_probs(circ: Circuit, f1q: float, f2q: float) -> np.ndarray:
    return np.array([
        (1 - f2q) if len(g.qubits) == 2 else (0.0 if g.name == "rz" else 1 - f1q) for g in circ.gates
    ])


def noisy_probabilities(
    circ: Circuit,
    f1q: float = 0.9998,
    f2q: float = 0.996,
    readout_error: float = 0.005,
    trajectories: int = 300,
    seed: int | None = 7,
) -> np.ndarray:
    """Distribución con ruido despolarizante por trayectorias de Monte Carlo (estimador estratificado).

    Optimización exacta en esperanza:
      * P₀ = Π(1−p_i) es la probabilidad de que no ocurra ningún error; ese término es
        la distribución ideal y se suma analíticamente (no se gasta ninguna trayectoria en él).
      * Las trayectorias restantes se condicionan a tener ≥1 error: la posición del primer
        error se muestrea de q_i = p_i Π_{j<i}(1−p_j) / (1−P₀) y la simulación arranca desde
        el estado ideal ya calculado tras la compuerta i (prefijos en caché).
    """
    rng = np.random.default_rng(seed)
    n = circ.n_qubits
    gates = circ.gates
    mats = _matrices(circ)
    p = _error_probs(circ, f1q, f2q)

    psi = np.zeros(1 << n, dtype=complex)
    psi[0] = 1.0
    prefix = [psi]
    for g, U in zip(gates, mats):
        psi = apply_gate(psi, n, g, U)
        prefix.append(psi)
    ideal = np.abs(prefix[-1]) ** 2

    survive = np.concatenate([[1.0], np.cumprod(1 - p)])  # Π_{j<i}(1−p_j)
    P0 = survive[-1]
    first = p * survive[:-1]
    if trajectories <= 0 or first.sum() <= 0:
        return apply_readout_error(ideal, n, readout_error)
    first = first / first.sum()

    acc = np.zeros(1 << n)
    for _ in range(trajectories):
        i0 = rng.choice(len(gates), p=first)
        psi = _apply_random_pauli(prefix[i0 + 1], n, gates[i0], rng)
        errs = rng.random(len(gates)) < p
        for i in range(i0 + 1, len(gates)):
            psi = apply_gate(psi, n, gates[i], mats[i])
            if errs[i]:
                psi = _apply_random_pauli(psi, n, gates[i], rng)
        acc += np.abs(psi) ** 2
    probs = P0 * ideal + (1 - P0) * acc / trajectories
    return apply_readout_error(probs, n, readout_error)


def _apply_random_pauli(psi: np.ndarray, n: int, g, rng) -> np.ndarray:
    if len(g.qubits) == 2:
        k = rng.integers(1, 16)  # Pauli de 2 qubits ≠ II (despolarizante)
        psi = apply_1q(psi, n, _PAULIS[k // 4], g.qubits[0])
        return apply_1q(psi, n, _PAULIS[k % 4], g.qubits[1])
    return apply_1q(psi, n, _PAULIS[rng.integers(1, 4)], g.qubits[0])


def apply_readout_error(probs: np.ndarray, n: int, eps: float) -> np.ndarray:
    """Matriz de confusión producto: cada bit se invierte con probabilidad eps."""
    if eps <= 0:
        return probs
    t = probs.reshape((2,) * n)
    M = np.array([[1 - eps, eps], [eps, 1 - eps]])
    for ax in range(n):
        t = np.moveaxis(np.tensordot(M, t, axes=([1], [ax])), 0, ax)
    return t.reshape(-1)


def sample_counts(probs: np.ndarray, shots: int, seed: int | None = None) -> dict[int, int]:
    rng = np.random.default_rng(seed)
    p = np.clip(probs, 0, None)
    p = p / p.sum()
    draws = rng.multinomial(shots, p)
    return {int(i): int(c) for i, c in enumerate(draws) if c}
