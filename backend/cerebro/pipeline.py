"""Servicios de alto nivel que usa la API (y los scripts).

    full_network_walk(...)     quantum walk exacto en las 302 neuronas (animación 3D)
    simulate_microcircuit(...) circuito para IonQ: exacto vs Trotter vs ruido Forte local
    autotune_steps(...)        elige los pasos de Trotter que minimizan el error total
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from . import config
from .analysis import neuron_marginals, postselect, summarize, tvd
from .circuits import (
    build_microcircuit,
    compile_native,
    lower_to_qis,
    noisy_probabilities,
    probabilities,
    sample_counts,
    to_ionq_input,
    to_openqasm2,
)
from .connectome import get_connectome
from .hamiltonian import arrival_times, evolve_exact, firing_probabilities, marginals
from .microcircuits import MICROCIRCUITS

Mode = Literal["trotter", "givens"]


# ---------------------------------------------------------------------------
# Red completa
# ---------------------------------------------------------------------------
def full_network_walk(
    source: str,
    theta: float = np.pi,
    gamma: float = 1.0,
    t_max: float = 60.0,
    frames: int = 120,
    weighting: str = "log",
) -> dict:
    C = get_connectome(weighting)  # type: ignore[arg-type]
    j = C.index(source)
    times = np.linspace(0.0, t_max, frames)
    P = firing_probabilities(C.eigh(), j, times, theta=theta, gamma=gamma)
    arr = arrival_times(P / max(np.sin(theta / 2) ** 2, 1e-12), times)
    # Participación efectiva (cuántas neuronas comparten la excitación) en cada instante
    q = P / np.maximum(P.sum(axis=1, keepdims=True), 1e-15)
    participation = 1.0 / np.sum(q**2, axis=1)
    return {
        "source": source,
        "theta": theta,
        "gamma": gamma,
        "fire_probability": float(np.sin(theta / 2) ** 2),
        "times": times.round(5).tolist(),
        "prob": np.round(P, 5).tolist(),
        "arrival_time": [None if np.isnan(a) else round(float(a), 4) for a in arr],
        "participation": participation.round(3).tolist(),
        "neurons": C.names,
    }


# ---------------------------------------------------------------------------
# Microcircuito (lo que va a IonQ)
# ---------------------------------------------------------------------------
def resolve_neurons(preset: str | None, neurons: list[str] | None) -> list[str]:
    if neurons:
        return list(neurons)
    if preset and preset in MICROCIRCUITS:
        return list(MICROCIRCUITS[preset].neurons)
    return list(MICROCIRCUITS["toque-6"].neurons)


def hardware_fidelity(n_2q: int, n_1q: int, f1q: float = config.FORTE_F1Q, f2q: float = config.FORTE_F2Q) -> float:
    """Estimación de primer orden: probabilidad de que ninguna compuerta falle."""
    return float(f2q**n_2q * f1q**n_1q)


def autotune_steps(
    J: np.ndarray,
    sources: list[int],
    theta: float,
    t: float,
    gamma: float = 1.0,
    order: int = 2,
    max_steps: int = 8,
) -> dict:
    """Elige r minimizando  ε(r) = TVD_Trotter(r) + (1 − F_hw(r)).

    El primer término cae como O(t³/r²) (2º orden); el segundo crece con el número
    de compuertas ∝ r. Hay un óptimo finito (docs/TEORIA.md §7).
    """
    exact = np.abs(evolve_exact(J, sources, theta, t, gamma)) ** 2
    table = []
    for r in range(1, max_steps + 1):
        c = build_microcircuit(J, sources, theta, t, gamma, "trotter", r, order)  # type: ignore[arg-type]
        nat = compile_native(c)
        e_trot = tvd(exact, probabilities(c))
        F = hardware_fidelity(nat.n_two_qubit, nat.n_one_qubit)
        table.append({"steps": r, "tvd_trotter": e_trot, "fidelity_hw": F, "zz": nat.n_two_qubit,
                      "gpi2": nat.n_one_qubit, "total_error": e_trot + (1 - F)})
    best = min(table, key=lambda row: row["total_error"])
    return {"best_steps": best["steps"], "table": table}


def simulate_microcircuit(
    preset: str | None = "toque-6",
    neurons: list[str] | None = None,
    sources: list[str] | None = None,
    theta: float = np.pi,
    t: float = 30.0,
    gamma: float = 1.0,
    mode: Mode = "trotter",
    steps: int | None = None,
    order: int = 2,
    shots: int = 1000,
    noisy: bool = True,
    trajectories: int = 200,
    seed: int | None = 11,
    weighting: str = "log",
) -> dict:
    C = get_connectome(weighting)  # type: ignore[arg-type]
    names = resolve_neurons(preset, neurons)
    n = len(names)
    if n > 16:
        raise ValueError("Máximo 16 neuronas en el simulador de microcircuitos.")
    J = C.sub_coupling(names)
    if not sources:
        default = MICROCIRCUITS[preset].default_source if preset in MICROCIRCUITS else names[0]
        sources = [default if default in names else names[0]]
    src = [names.index(s) for s in sources]
    k = len(src)

    tuning = None
    if mode == "trotter" and not steps:
        max_steps = 8 if n <= 7 else (4 if n <= 10 else 3)  # el costo clásico crece como 2^n
        tuning = autotune_steps(J, src, theta, t, gamma, order, max_steps=max_steps)
        steps = tuning["best_steps"]
    steps = int(steps or 1)

    logical = build_microcircuit(J, src, theta, t, gamma, mode, steps, order, labels=names)  # type: ignore[arg-type]
    native = compile_native(logical)
    qis = lower_to_qis(logical)

    exact = np.abs(evolve_exact(J, src, theta, t, gamma)) ** 2
    ideal = probabilities(logical)
    result: dict = {
        "neurons": names,
        "sources": sources,
        "n_qubits": n,
        "theta": theta,
        "t": t,
        "gamma": gamma,
        "mode": mode,
        "steps": steps,
        "order": order,
        "coupling": [[round(float(x), 6) for x in row] for row in J],
        "exact": {"marginals": neuron_marginals(exact, n).tolist()},
        "circuit_ideal": {"marginals": neuron_marginals(ideal, n).tolist(), "tvd_vs_exact": tvd(exact, ideal)},
        "resources": {
            "zz_gates": native.n_two_qubit,
            "gpi_gates": native.n_one_qubit,
            "fidelity_estimate": hardware_fidelity(native.n_two_qubit, native.n_one_qubit),
            "logical_hops": sum(1 for g in logical.gates if g.name == "hop"),
            "qis_cnots": sum(1 for g in qis.gates if g.name == "cnot"),
        },
        "autotune": tuning,
        "circuit": {
            "logical": logical.to_dict(),
            "ionq_native": to_ionq_input(native),
            "ionq_qis": to_ionq_input(qis),
            "openqasm2": to_openqasm2(qis),
        },
    }
    if noisy and n > 10:
        result["noisy_local_note"] = "Simulación con ruido omitida para más de 10 qubits (costo clásico 2^n)."
    if noisy and n <= 10:
        trajectories = trajectories if n <= 8 else max(60, trajectories // 2)
        noisy_p = noisy_probabilities(
            native, config.FORTE_F1Q, config.FORTE_F2Q, config.FORTE_READOUT_ERROR, trajectories, seed
        )
        counts = sample_counts(noisy_p, shots, seed)
        from .analysis import counts_to_probs

        measured = counts_to_probs(counts, n)
        result["noisy_local"] = {
            "shots": shots,
            "counts": {format(kk, f"0{n}b")[::-1]: v for kk, v in counts.items()},
            **summarize(exact, measured, n, k),
        }
    # Serie temporal exacta de las poblaciones (para graficar)
    ts = np.linspace(0, max(t * 1.5, 1.0), 61)
    if k == 1:  # sector de una excitación: fórmula cerrada P_k(t) = sin²(θ/2)|[e^{-iγJt}]_kj|²
        series = firing_probabilities(np.linalg.eigh(J), src[0], ts, theta, gamma).tolist()
    else:
        series = [marginals(np.abs(evolve_exact(J, src, theta, float(tt), gamma)) ** 2, n).tolist() for tt in ts]
    result["exact_series"] = {"times": ts.round(4).tolist(), "marginals": series}
    return result


def postselected_marginals(probs: np.ndarray, n: int, k: int) -> list[float]:
    ps, _ = postselect(probs, n, k)
    return neuron_marginals(ps, n).tolist()
