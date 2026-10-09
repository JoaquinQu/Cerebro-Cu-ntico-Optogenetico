"""Simulador de vector de estado (ideal y con ruido tipo IonQ) sin dependencias externas.

Ruido (modelo simple, docs/TEORIA.md §7):
    * Tras cada compuerta de 2 qubits: canal despolarizante de 2 qubits con
      probabilidad p2 = 1 - F2Q (Forte: F2Q ≈ 0.996).
    * Tras cada compuerta física de 1 qubit: despolarizante con p1 = 1 - F1Q.
      Las RZ son virtuales y no llevan ruido.
    * Error de lectura simétrico por qubit (bit-flip clásico en el resultado).
Se simula con trayectorias de Monte Carlo (Paulis aleatorios insertados), lo que
reproduce el canal en promedio y escala a ~16 qubits sin matrices densidad.
"""

from __future__ import annotations

import numpy as np

from .ir import Circuit, I2, X, Y, Z

_PAULIS = [I2, X, Y, Z]


def apply_1q(psi: np.ndarray, n: int, U: np.ndarray, q: int) -> np.ndarray:
    t = psi.reshape((2,) * n)
    ax = n - 1 - q
    t = np.tensordot(U, t, axes=([1], [ax]))
    t = np.moveaxis(t, 0, ax)
    return t.reshape(-1)


def apply_2q(psi: np.ndarray, n: int, U: np.ndarray, a: int, b: int) -> np.ndarray:
    t = psi.reshape((2,) * n)
    axa, axb = n - 1 - a, n - 1 - b
    U4 = U.reshape(2, 2, 2, 2)
    t = np.tensordot(U4, t, axes=([2, 3], [axa, axb]))
    t = np.moveaxis(t, [0, 1], [axa, axb])
    return t.reshape(-1)


def apply_gate(psi: np.ndarray, n: int, gate) -> np.ndarray:
    U = gate.matrix
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
    for g in circ.gates:
        psi = apply_gate(psi, n, g)
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


def noisy_probabilities(
    circ: Circuit,
    f1q: float = 0.9998,
    f2q: float = 0.996,
    readout_error: float = 0.005,
    trajectories: int = 300,
    seed: int | None = 7,
) -> np.ndarray:
    """Distribución promedio sobre trayectorias con errores de Pauli aleatorios."""
    rng = np.random.default_rng(seed)
    n = circ.n_qubits
    p1, p2 = 1 - f1q, 1 - f2q
    acc = np.zeros(1 << n)
    for _ in range(trajectories):
        psi = np.zeros(1 << n, dtype=complex)
        psi[0] = 1.0
        for g in circ.gates:
            psi = apply_gate(psi, n, g)
            if len(g.qubits) == 2 and rng.random() < p2:
                # Pauli de 2 qubits aleatorio distinto de II (despolarizante)
                k = rng.integers(1, 16)
                pa, pb = _PAULIS[k // 4], _PAULIS[k % 4]
                psi = apply_1q(psi, n, pa, g.qubits[0])
                psi = apply_1q(psi, n, pb, g.qubits[1])
            elif len(g.qubits) == 1 and g.name != "rz" and rng.random() < p1:
                psi = apply_1q(psi, n, _PAULIS[rng.integers(1, 4)], g.qubits[0])
        acc += np.abs(psi) ** 2
    probs = acc / trajectories
    return apply_readout_error(probs, n, readout_error)


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
