"""Constructores de circuitos para el microcircuito (docs/TEORIA.md §4–§6).

Tres piezas:
    laser(...)       pulso optogenético:  RX(θ) en cada neurona iluminada,
                     θ = Ω·τ (frecuencia de Rabi × duración del pulso).
    trotter_xy(...)  e^{-iHt} con H = γ Σ J_ij (XX+YY)/2 por fórmula de
                     Trotter–Suzuki de 1er o 2º orden. Cada término es una
                     compuerta  hop(α) = exp(-iα(XX+YY)/2),  α = γ J_ij δt.
    givens_walk(...) modo "compilado": prepara exactamente la distribución del
                     quantum walk de una excitación con n-1 rotaciones de Givens
                     (requiere conocer e^{-iγJt}|j⟩ clásicamente; ver §6.3).
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from .ir import Circuit, Gate

Order = Literal[1, 2]


def coupling_edges(J: np.ndarray, min_weight: float = 0.0) -> list[tuple[int, int, float]]:
    n = len(J)
    return [
        (i, j, float(J[i, j])) for i in range(n) for j in range(i + 1, n) if J[i, j] > min_weight
    ]


def laser(circ: Circuit, sources: list[int], theta: float) -> Circuit:
    for q in sources:
        circ.add("rx", [q], [theta], tag="laser")
    return circ


def _merge_adjacent_hops(gates: list[Gate]) -> list[Gate]:
    """Fusiona hops consecutivos sobre el mismo par (exacto: conmutan consigo mismos)."""
    out: list[Gate] = []
    for g in gates:
        if (
            out
            and g.name == "hop"
            and out[-1].name == "hop"
            and set(out[-1].qubits) == set(g.qubits)
        ):
            prev = out.pop()
            out.append(Gate("hop", prev.qubits, (prev.params[0] + g.params[0],), prev.tag))
        else:
            out.append(g)
    return out


def trotter_xy(
    J: np.ndarray,
    t: float,
    steps: int,
    gamma: float = 1.0,
    order: Order = 2,
    min_weight: float = 0.0,
) -> Circuit:
    """Circuito de Trotter para e^{-iHt}, H = γ Σ_{i<j} J_ij (XX+YY)/2."""
    n = len(J)
    circ = Circuit(n)
    edges = coupling_edges(J, min_weight)
    if t == 0 or not edges or steps < 1:
        return circ
    dt = t / steps
    gates: list[Gate] = []
    for s in range(steps):
        tag = f"trotter-{s + 1}"
        if order == 1:
            for i, j, w in edges:
                gates.append(Gate("hop", (i, j), (gamma * w * dt,), tag))
        else:  # Strang: Π_e e^{-ih_e δ/2} · Π_{e reverso} e^{-ih_e δ/2}
            for i, j, w in edges:
                gates.append(Gate("hop", (i, j), (gamma * w * dt / 2,), tag))
            for i, j, w in reversed(edges):
                gates.append(Gate("hop", (i, j), (gamma * w * dt / 2,), tag))
    circ.gates = _merge_adjacent_hops(gates)
    circ.meta = {"kind": "trotter", "t": t, "steps": steps, "order": order, "gamma": gamma,
                 "edges": len(edges), "min_weight": min_weight}
    return circ


def givens_walk(target: np.ndarray, source: int) -> Circuit:
    """Rotaciones de Givens que llevan |e_source⟩ → Σ_k |v_k| |e_k⟩ (módulos exactos).

    Cascada: la excitación empieza en `source`; en cada paso una compuerta hop(α_m)
    deja |v_{o_m}| en el qubit o_m y pasa el resto al siguiente qubit o_{m+1}.
        cos α_m = |v_{o_m}| / R_m ,   R_{m+1} = R_m sin α_m ,   R_0 = 1.
    Las fases no se reproducen (irrelevantes al medir en base Z).
    """
    v = np.abs(np.asarray(target))
    v = v / np.linalg.norm(v)
    n = len(v)
    others = [k for k in np.argsort(-v) if k != source]
    order = [source] + [int(k) for k in others]
    circ = Circuit(n)
    R = 1.0
    for m in range(n - 1):
        a, b = order[m], order[m + 1]
        if R < 1e-12:
            break
        c = np.clip(v[a] / R, 0.0, 1.0)
        alpha = float(np.arccos(c))
        if alpha > 1e-9:
            circ.add("hop", [a, b], [alpha], tag=f"givens-{m + 1}")
        R = R * np.sin(alpha)
    circ.meta = {"kind": "givens", "source": source, "order": order}
    return circ


def build_microcircuit(
    J: np.ndarray,
    sources: list[int],
    theta: float,
    t: float,
    gamma: float = 1.0,
    mode: Literal["trotter", "givens"] = "trotter",
    steps: int = 3,
    order: Order = 2,
    min_weight: float = 0.0,
    labels: list[str] | None = None,
) -> Circuit:
    """Láser + evolución: el circuito lógico completo que se envía a IonQ."""
    n = len(J)
    circ = Circuit(n, labels=list(labels or []))
    laser(circ, sources, theta)
    if mode == "trotter":
        evo = trotter_xy(J, t, steps, gamma, order, min_weight)
    elif mode == "givens":
        if len(sources) != 1:
            raise ValueError("El modo 'givens' sólo admite un láser (sector de una excitación).")
        lam, V = np.linalg.eigh(J)
        amp = V @ (np.exp(-1j * gamma * lam * t) * V[sources[0]])
        evo = givens_walk(amp, sources[0])
    else:
        raise ValueError(mode)
    circ.extend(evo)
    circ.meta = {**evo.meta, "theta": theta, "sources": sources, "mode": mode}
    return circ
