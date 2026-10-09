"""Compilación del IR a IonQ (docs/TEORIA.md §6.4).

Dos salidas, ambas en el formato `ionq.circuit.v1` de la API v0.4:

1. **native / Forte** (recomendada): GPi, GPi2, ZZ(θ) y Z virtual propagada.
       hop(α) = exp(-iα/2·XX)·exp(-iα/2·YY)
       exp(-iβ·XX) = (V⊗V)·ZZ(β/π)·(V†⊗V†),   V = GPi2(1/4) = RY(π/2)
       exp(-iβ·YY) = (W⊗W)·ZZ(β/π)·(W†⊗W†),   W = GPi2(0)   = RX(π/2)
       RX(θ)       = GPi2(1/4) · RZ(θ) · GPi2(3/4)
   ⇒ cada salto cuesta exactamente 2 compuertas ZZ.
   Las RZ se eliminan por "propagación de fase":
       GPi2(φ)·RZ(θ) = RZ(θ)·GPi2(φ − θ/2π)   (igual para GPi; ZZ conmuta con Z)
   y las RZ que quedan al final no afectan la medición en base Z.

2. **qis** (portátil): h, rx, rz, cnot (IonQ recompila a nativas en su servidor).
       exp(-iβ·ZZ) = CNOT·(I⊗RZ(2β))·CNOT

Para Aria (MS parcial) también se ofrece `target="aria"`:
       exp(-iβ·XX) = MS(0, 0, β/π),  exp(-iβ·YY) = MS(1/4, 1/4, β/π)   (β ≤ π/4).
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from .ir import Circuit, Gate

Target = Literal["forte", "aria"]

TWO_PI = 2 * np.pi


# ---------------------------------------------------------------------------
# Bajada (lowering) a compuertas nativas
# ---------------------------------------------------------------------------
def _zz_native(a: int, b: int, theta_turns: float, tag: str) -> list[Gate]:
    """ZZ(θ) con θ reducido a [0, 1/4] usando identidades exactas.

    * ZZ(θ+1)   = −ZZ(θ)                          (fase global)
    * ZZ(θ+1/2) = −i·(Z⊗Z)·ZZ(θ)   y  Z ≅ RZ(π)  (virtual, gratis)
    * ZZ(−θ)    = (X⊗I)·ZZ(θ)·(X⊗I),  X ≅ GPi(0)
    """
    pre: list[Gate] = []
    post: list[Gate] = []
    th = (theta_turns + 0.5) % 1.0 - 0.5  # (−1/2, 1/2]
    if th > 0.25:
        th -= 0.5
        post += [Gate("rz", (a,), (np.pi,), tag), Gate("rz", (b,), (np.pi,), tag)]
    elif th < -0.25:
        th += 0.5
        post += [Gate("rz", (a,), (np.pi,), tag), Gate("rz", (b,), (np.pi,), tag)]
    if th < 0:
        th = -th
        pre.append(Gate("gpi", (a,), (0.0,), tag))
        post.insert(0, Gate("gpi", (a,), (0.0,), tag))
    return pre + [Gate("zz", (a, b), (th,), tag)] + post


def lower_to_native(circ: Circuit, target: Target = "forte") -> Circuit:
    out = Circuit(circ.n_qubits, labels=list(circ.labels), meta={**circ.meta, "target": target})
    g_ = out.gates
    for g in circ.gates:
        tag = g.tag
        if g.name in ("gpi", "gpi2", "zz", "ms", "rz"):
            g_.append(g)
        elif g.name == "rx":
            (q,) = g.qubits
            g_ += [Gate("gpi2", (q,), (0.75,), tag), Gate("rz", (q,), (g.params[0],), tag),
                   Gate("gpi2", (q,), (0.25,), tag)]
        elif g.name == "ry":
            (q,) = g.qubits  # RY(θ) = RX(π/2)·RZ(θ)·RX(−π/2)  (rota ẑ→ŷ… verificado en tests)
            g_ += [Gate("gpi2", (q,), (0.0,), tag), Gate("rz", (q,), (g.params[0],), tag),
                   Gate("gpi2", (q,), (0.5,), tag)]
        elif g.name == "x":
            g_.append(Gate("gpi", g.qubits, (0.0,), tag))
        elif g.name == "hop":
            a, b = g.qubits
            beta = g.params[0] / 2  # exp(-iβXX)·exp(-iβYY)
            if target == "aria":
                if abs(beta) > np.pi / 4 + 1e-12:
                    raise ValueError("Ángulo demasiado grande para MS parcial; aumenta los pasos de Trotter.")
                # MS(φ0+½, φ1, θ) = MS(φ0, φ1, −θ): un ángulo negativo se absorbe en la fase
                s = 0.5 if beta < 0 else 0.0
                th = abs(beta) / np.pi
                g_ += [Gate("ms", (a, b), (0.0 + s, 0.0, th), tag),
                       Gate("ms", (a, b), (0.25 + s, 0.25, th), tag)]
            else:
                th = beta / np.pi
                # XX: V† … ZZ … V   con V = GPi2(1/4), V† = GPi2(3/4)
                g_ += [Gate("gpi2", (a,), (0.75,), tag), Gate("gpi2", (b,), (0.75,), tag)]
                g_ += _zz_native(a, b, th, tag)
                g_ += [Gate("gpi2", (a,), (0.25,), tag), Gate("gpi2", (b,), (0.25,), tag)]
                # YY: W† … ZZ … W   con W = GPi2(0), W† = GPi2(1/2)
                g_ += [Gate("gpi2", (a,), (0.5,), tag), Gate("gpi2", (b,), (0.5,), tag)]
                g_ += _zz_native(a, b, th, tag)
                g_ += [Gate("gpi2", (a,), (0.0,), tag), Gate("gpi2", (b,), (0.0,), tag)]
        else:
            raise ValueError(f"No sé bajar '{g.name}' a nativas")
    return out


def _single_qubit_matrix(gates: list[Gate]) -> np.ndarray:
    U = np.eye(2, dtype=complex)
    for g in gates:
        U = g.matrix @ U
    return U


def cancel_inverse_pairs(circ: Circuit) -> Circuit:
    """Optimización mínima: elimina pares GPi2(φ)·GPi2(φ+½) consecutivos en un qubit
    (son inversos) y fusiona RZ consecutivas. Exacta."""
    out: list[Gate] = []
    last_on: dict[int, int] = {}  # qubit -> índice en out de la última compuerta que lo toca
    for g in circ.gates:
        if len(g.qubits) == 1:
            q = g.qubits[0]
            k = last_on.get(q)
            if k is not None and out[k] is not None and len(out[k].qubits) == 1:
                prev = out[k]
                if (prev.name == g.name == "gpi2"
                        and abs(((prev.params[0] - g.params[0]) % 1.0) - 0.5) < 1e-12):
                    out[k] = None  # se cancelan
                    # buscar la compuerta anterior sobre q
                    last_on.pop(q)
                    for idx in range(k - 1, -1, -1):
                        if out[idx] is not None and q in out[idx].qubits:
                            last_on[q] = idx
                            break
                    continue
                if prev.name == g.name == "rz":
                    out[k] = Gate("rz", (q,), (prev.params[0] + g.params[0],), prev.tag)
                    continue
            out.append(g)
            last_on[q] = len(out) - 1
        else:
            out.append(g)
            for q in g.qubits:
                last_on[q] = len(out) - 1
    res = circ.copy()
    res.gates = [g for g in out if g is not None]
    return res


def propagate_virtual_z(circ: Circuit) -> tuple[Circuit, np.ndarray]:
    """Elimina las RZ empujándolas hacia el final. Devuelve (circuito, fases finales).

    Circuito original = RZ(fases) · circuito_sin_rz  (las RZ finales no cambian
    las probabilidades medidas en base Z).
    """
    frame = np.zeros(circ.n_qubits)
    out = Circuit(circ.n_qubits, labels=list(circ.labels), meta=dict(circ.meta))
    for g in circ.gates:
        if g.name == "rz":
            frame[g.qubits[0]] += g.params[0]
        elif g.name in ("gpi", "gpi2"):
            q = g.qubits[0]
            phi = (g.params[0] - frame[q] / TWO_PI) % 1.0
            out.gates.append(Gate(g.name, g.qubits, (phi,), g.tag))
        elif g.name == "ms":
            a, b = g.qubits
            p0 = (g.params[0] - frame[a] / TWO_PI) % 1.0
            p1 = (g.params[1] - frame[b] / TWO_PI) % 1.0
            out.gates.append(Gate("ms", g.qubits, (p0, p1, *g.params[2:]), g.tag))
        elif g.name == "zz":
            out.gates.append(g)
        else:
            raise ValueError(f"'{g.name}' no es nativa; usa lower_to_native primero")
    return out, frame


def _zyz(U: np.ndarray) -> tuple[float, float, float]:
    """U ≅ RZ(a)·RY(b)·RZ(c) (módulo fase global)."""
    Up = U / np.sqrt(np.linalg.det(U))
    b = 2 * np.arctan2(abs(Up[1, 0]), abs(Up[0, 0]))
    if abs(np.sin(b / 2)) < 1e-10:
        s, d = float(np.angle(Up[1, 1]) - np.angle(Up[0, 0])), 0.0
    elif abs(np.cos(b / 2)) < 1e-10:
        s, d = 0.0, float(np.angle(Up[1, 0]) - np.angle(-Up[0, 1]))
    else:
        s = float(np.angle(Up[1, 1]) - np.angle(Up[0, 0]))
        d = float(np.angle(Up[1, 0]) - np.angle(-Up[0, 1]))
    a, c = (s + d) / 2, (s - d) / 2
    return a, float(b), c


def _synth_1q(U: np.ndarray, q: int, tag: str) -> list[Gate]:
    """Síntesis mínima en nativas: 0, 1 o 2 pulsos físicos + RZ virtuales (orden temporal)."""
    a, b, c = _zyz(U)
    tol = 1e-9
    bm = (b + np.pi) % (2 * np.pi) - np.pi
    if abs(bm) < tol:  # diagonal
        return [Gate("rz", (q,), (a + c,), tag)]
    if abs(abs(bm) - np.pi / 2) < tol:  # RY(±π/2) = GPi2(1/4) ó GPi2(3/4)
        ph = 0.25 if bm > 0 else 0.75
        return [Gate("rz", (q,), (c,), tag), Gate("gpi2", (q,), (ph,), tag), Gate("rz", (q,), (a,), tag)]
    if abs(abs(bm) - np.pi) < tol:  # RY(π) ≅ GPi(1/4)
        return [Gate("rz", (q,), (c,), tag), Gate("gpi", (q,), (0.25,), tag), Gate("rz", (q,), (a,), tag)]
    # RY(b) = RX(π/2)·RZ(−b)·RX(−π/2),  RX(±π/2) = GPi2(0) / GPi2(1/2)
    return [Gate("rz", (q,), (c,), tag), Gate("gpi2", (q,), (0.5,), tag), Gate("rz", (q,), (-b,), tag),
            Gate("gpi2", (q,), (0.0,), tag), Gate("rz", (q,), (a,), tag)]


def resynthesize_1q(circ: Circuit) -> Circuit:
    """Fusiona cada racha de compuertas de 1 qubit y la re-sintetiza con ≤ 2 pulsos."""
    out: list[Gate] = []
    pending: dict[int, list[Gate]] = {}

    def flush(q: int) -> None:
        run = pending.pop(q, [])
        if not run:
            return
        if len(run) == 1 and run[0].name == "rz":
            out.append(run[0])
            return
        U = np.eye(2, dtype=complex)
        for g in run:
            U = g.matrix @ U
        out.extend(_synth_1q(U, q, run[0].tag))

    for g in circ.gates:
        if len(g.qubits) == 1:
            pending.setdefault(g.qubits[0], []).append(g)
        else:
            for q in g.qubits:
                flush(q)
            out.append(g)
    for q in list(pending):
        flush(q)
    res = circ.copy()
    res.gates = out
    return res


def compile_native(circ: Circuit, target: Target = "forte", optimize: bool = True) -> Circuit:
    low = lower_to_native(circ, target)
    if optimize:
        low = resynthesize_1q(low)
    nat, _ = propagate_virtual_z(low)
    nat.meta = {**nat.meta, "target": target}
    return nat


# ---------------------------------------------------------------------------
# Compuertas QIS (portables)
# ---------------------------------------------------------------------------
def lower_to_qis(circ: Circuit) -> Circuit:
    out = Circuit(circ.n_qubits, labels=list(circ.labels), meta={**circ.meta, "gateset": "qis"})
    g_ = out.gates
    for g in circ.gates:
        tag = g.tag
        if g.name in ("h", "x", "rx", "ry", "rz", "cnot"):
            g_.append(g)
        elif g.name == "hop":
            a, b = g.qubits
            beta = g.params[0] / 2
            zz = [Gate("cnot", (a, b), (), tag), Gate("rz", (b,), (2 * beta,), tag),
                  Gate("cnot", (a, b), (), tag)]
            g_ += [Gate("h", (a,), (), tag), Gate("h", (b,), (), tag), *zz,
                   Gate("h", (a,), (), tag), Gate("h", (b,), (), tag)]
            g_ += [Gate("rx", (a,), (-np.pi / 2,), tag), Gate("rx", (b,), (-np.pi / 2,), tag), *zz,
                   Gate("rx", (a,), (np.pi / 2,), tag), Gate("rx", (b,), (np.pi / 2,), tag)]
        else:
            raise ValueError(f"No sé bajar '{g.name}' a QIS")
    return out


# ---------------------------------------------------------------------------
# Serialización al formato de la API de IonQ
# ---------------------------------------------------------------------------
def _r(x: float, nd: int = 6) -> float:
    return float(round(x, nd))


def to_ionq_input(circ: Circuit) -> dict:
    """Bloque `input` de un trabajo `ionq.circuit.v1` (native o qis según el contenido)."""
    names = {g.name for g in circ.gates}
    native = names <= {"gpi", "gpi2", "zz", "ms"}
    ops = []
    for g in circ.gates:
        if g.name in ("gpi", "gpi2"):
            ops.append({"gate": g.name, "target": g.qubits[0], "phase": _r(g.params[0] % 1.0)})
        elif g.name == "zz":
            ops.append({"gate": "zz", "targets": list(g.qubits), "angle": _r(g.params[0])})
        elif g.name == "ms":
            op = {"gate": "ms", "targets": list(g.qubits), "phases": [_r(g.params[0]), _r(g.params[1])]}
            if len(g.params) > 2:
                op["angle"] = _r(g.params[2])
            ops.append(op)
        elif g.name == "cnot":
            ops.append({"gate": "cnot", "control": g.qubits[0], "target": g.qubits[1]})
        elif g.name in ("rx", "ry", "rz"):
            ops.append({"gate": g.name, "target": g.qubits[0], "rotation": _r(g.params[0], 8)})
        elif g.name in ("h", "x"):
            ops.append({"gate": g.name, "target": g.qubits[0]})
        else:
            raise ValueError(f"'{g.name}' no se puede serializar para IonQ")
    return {"qubits": circ.n_qubits, "gateset": "native" if native else "qis", "circuit": ops}


def to_openqasm2(circ: Circuit) -> str:
    """Exporta un circuito QIS a OpenQASM 2.0 (útil para Qiskit/Braket)."""
    lines = ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{circ.n_qubits}];",
             f"creg c[{circ.n_qubits}];"]
    for g in circ.gates:
        q = g.qubits
        if g.name == "cnot":
            lines.append(f"cx q[{q[0]}],q[{q[1]}];")
        elif g.name in ("rx", "ry", "rz"):
            lines.append(f"{g.name}({g.params[0]:.10f}) q[{q[0]}];")
        elif g.name in ("h", "x"):
            lines.append(f"{g.name} q[{q[0]}];")
        else:
            raise ValueError("Exporta primero con lower_to_qis()")
    lines.append("measure q -> c;")
    return "\n".join(lines) + "\n"
