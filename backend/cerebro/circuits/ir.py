"""Representación intermedia (IR) de circuitos y matrices de compuertas.

Convenciones (verificadas en tests/test_compilation.py):
    * Qubit q = bit q del índice de la base (q0 = bit menos significativo).
    * Una compuerta de 2 qubits sobre (a, b) usa la matriz en la base |b_a b_b⟩,
      es decir  kron(op_a, op_b)  con  a  como factor izquierdo.
    * Compuertas nativas de IonQ con fases en *vueltas* (1 vuelta = 2π rad),
      según docs.ionq.com/guides/getting-started-with-native-gates:
          GPi(φ)        = [[0, e^{-2πiφ}], [e^{2πiφ}, 0]]
          GPi2(φ)       = (1/√2) [[1, -i e^{-2πiφ}], [-i e^{2πiφ}, 1]]
          MS(φ0,φ1,θ)   = exp(-iπθ σ_φ0 ⊗ σ_φ1)                  (Aria)
          ZZ(θ)         = exp(-iπθ Z⊗Z)                          (Forte)
          VirtualZ(θ)   = diag(e^{-iπθ}, e^{iπθ})  ≡ RZ(2πθ)
    * Compuertas QIS (ángulos en radianes): h, x, rx, ry, rz, cnot.
    * Compuerta de alto nivel  hop(α) = exp(-i α (XX+YY)/2)  (salto de excitación).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

I2 = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.array([[1, 0], [0, -1]], dtype=complex)
H_MAT = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)


def _sigma(phi_turns: float) -> np.ndarray:
    a = 2 * np.pi * phi_turns
    return np.array([[0, np.exp(-1j * a)], [np.exp(1j * a), 0]], dtype=complex)


def _expm_herm(Hm: np.ndarray, theta: float) -> np.ndarray:
    """exp(-iθH) para H hermítica con H² = 1 (productos de Pauli)."""
    return np.cos(theta) * np.eye(len(Hm)) - 1j * np.sin(theta) * Hm


ONE_QUBIT = {"gpi", "gpi2", "rz", "rx", "ry", "h", "x"}
TWO_QUBIT = {"zz", "ms", "cnot", "hop", "rxx", "ryy"}
NATIVE_FORTE = {"gpi", "gpi2", "zz", "rz"}
NATIVE_ARIA = {"gpi", "gpi2", "ms", "rz"}
QIS = {"h", "x", "rx", "ry", "rz", "cnot"}


def gate_matrix(name: str, params: tuple[float, ...]) -> np.ndarray:
    if name == "gpi":
        return _sigma(params[0])
    if name == "gpi2":
        return (I2 - 1j * _sigma(params[0])) / np.sqrt(2)
    if name == "rz":
        t = params[0]
        return np.diag([np.exp(-1j * t / 2), np.exp(1j * t / 2)])
    if name == "rx":
        return _expm_herm(X, params[0] / 2)
    if name == "ry":
        return _expm_herm(Y, params[0] / 2)
    if name == "h":
        return H_MAT
    if name == "x":
        return X
    if name == "zz":
        return _expm_herm(np.kron(Z, Z), np.pi * params[0])
    if name == "ms":
        phi0, phi1 = params[0], params[1]
        theta = params[2] if len(params) > 2 else 0.25
        return _expm_herm(np.kron(_sigma(phi0), _sigma(phi1)), np.pi * theta)
    if name == "cnot":  # control = primer qubit
        return np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=complex)
    if name == "rxx":
        return _expm_herm(np.kron(X, X), params[0] / 2)
    if name == "ryy":
        return _expm_herm(np.kron(Y, Y), params[0] / 2)
    if name == "hop":
        a = params[0]
        # exp(-iα(XX+YY)/2): XX y YY conmutan ⇒ producto exacto
        return _expm_herm(np.kron(X, X), a / 2) @ _expm_herm(np.kron(Y, Y), a / 2)
    raise ValueError(f"Compuerta desconocida: {name}")


@dataclass(frozen=True)
class Gate:
    name: str
    qubits: tuple[int, ...]
    params: tuple[float, ...] = ()
    tag: str = ""  # etiqueta opcional (p.ej. "laser", "trotter-3") para el frontend

    @property
    def matrix(self) -> np.ndarray:
        return gate_matrix(self.name, self.params)


@dataclass
class Circuit:
    n_qubits: int
    gates: list[Gate] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)  # nombre de la neurona de cada qubit
    meta: dict = field(default_factory=dict)

    def add(self, name: str, qubits: Iterable[int], params: Iterable[float] = (), tag: str = "") -> "Circuit":
        q = tuple(int(x) for x in qubits)
        if any(not 0 <= x < self.n_qubits for x in q):
            raise ValueError(f"qubit fuera de rango en {name}{q}")
        self.gates.append(Gate(name, q, tuple(float(p) for p in params), tag))
        return self

    def extend(self, other: "Circuit") -> "Circuit":
        self.gates.extend(other.gates)
        return self

    def copy(self) -> "Circuit":
        return Circuit(self.n_qubits, list(self.gates), list(self.labels), dict(self.meta))

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for g in self.gates:
            out[g.name] = out.get(g.name, 0) + 1
        return out

    @property
    def n_two_qubit(self) -> int:
        return sum(1 for g in self.gates if len(g.qubits) == 2)

    @property
    def n_one_qubit(self) -> int:
        # rz es virtual en IonQ (no cuesta tiempo ni error)
        return sum(1 for g in self.gates if len(g.qubits) == 1 and g.name != "rz")

    def to_dict(self) -> dict:
        return {
            "n_qubits": self.n_qubits,
            "labels": self.labels,
            "gates": [
                {"name": g.name, "qubits": list(g.qubits), "params": list(g.params), "tag": g.tag}
                for g in self.gates
            ],
            "counts": self.counts(),
            "two_qubit_gates": self.n_two_qubit,
            "one_qubit_gates": self.n_one_qubit,
            "meta": self.meta,
        }
