"""Presupuesto de recursos para IonQ Forte de cada microcircuito.

    python scripts/resource_report.py            # tabla en markdown
    python scripts/resource_report.py --t 40

Para cada microcircuito: qubits, conexiones, pasos de Trotter óptimos
(minimizan TVD_Trotter + (1 − F_hw)), compuertas ZZ/GPi2 nativas, fidelidad
estimada y el costo del modo compilado (Givens).
"""

import argparse

import _path  # noqa: F401
import numpy as np

from cerebro.circuits import build_microcircuit, compile_native, probabilities
from cerebro.connectome import get_connectome
from cerebro.hamiltonian import evolve_exact
from cerebro.analysis import tvd
from cerebro.microcircuits import MICROCIRCUITS
from cerebro.pipeline import autotune_steps, hardware_fidelity


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t", type=float, default=30.0)
    ap.add_argument("--max-steps", type=int, default=6)
    args = ap.parse_args()
    C = get_connectome()
    print(f"\nt = {args.t:g} (unidades de 1/γ), láser θ = π en la neurona por defecto\n")
    print("| Microcircuito | qubits | conexiones | r óptimo | ZZ (Trotter) | GPi2 | F_hw estimada "
          "| TVD Trotter | ZZ (Givens) | F_hw Givens |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for m in MICROCIRCUITS.values():
        names = list(m.neurons)
        J = C.sub_coupling(names)
        src = [names.index(m.default_source)]
        tune = autotune_steps(J, src, np.pi, args.t, max_steps=args.max_steps)
        best = next(r for r in tune["table"] if r["steps"] == tune["best_steps"])
        g = compile_native(build_microcircuit(J, src, np.pi, args.t, mode="givens"))
        exact = np.abs(evolve_exact(J, src, np.pi, args.t)) ** 2
        assert tvd(probabilities(g), exact) < 1e-9
        edges = int((np.triu(J, 1) > 0).sum())
        print(f"| {m.id} | {len(names)} | {edges} | {best['steps']} | {best['zz']} | {best['gpi2']} | "
              f"{best['fidelity_hw']:.2f} | {best['tvd_trotter']:.3f} | {g.n_two_qubit} | "
              f"{hardware_fidelity(g.n_two_qubit, g.n_one_qubit):.2f} |")


if __name__ == "__main__":
    main()
