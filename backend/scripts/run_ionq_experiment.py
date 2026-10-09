"""Experimento en IonQ: dinámica del microcircuito de toque en varios tiempos.

Ejemplos
    # 1) Simulador de IonQ con modelo de ruido de Forte (sin costo de QPU)
    python scripts/run_ionq_experiment.py --backend simulator --noise forte-1

    # 2) Ver el circuito y los recursos sin enviar nada
    python scripts/run_ionq_experiment.py --dry-run

    # 3) Hardware real (requiere ALLOW_QPU=true en backend/.env y confirmación)
    python scripts/run_ionq_experiment.py --backend qpu.forte-1 --times 10 20 30 --shots 500

Buenas prácticas de IonQ aplicadas (docs/TEORIA.md §8):
    * mismo número de pasos de Trotter para todos los tiempos;
    * post-selección por conservación del número de excitaciones;
    * calibración del orden de bits antes de interpretar resultados.
"""

import argparse
import json
import sys

import _path  # noqa: F401
import numpy as np

from cerebro import config
from cerebro.circuits import build_microcircuit, compile_native, lower_to_qis, to_ionq_input
from cerebro.connectome import get_connectome
from cerebro.ionq import QPU_BACKENDS, IonQClient
from cerebro.ionq import experiment
from cerebro.microcircuits import MICROCIRCUITS
from cerebro.pipeline import hardware_fidelity


def parse() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", default="simulator", help="simulator | qpu.forte-1 | qpu.forte-enterprise-1")
    ap.add_argument("--noise", default=config.DEFAULT_NOISE_MODEL, help="modelo de ruido del simulador (forte-1, aria-1, ideal)")
    ap.add_argument("--preset", default="toque-6", choices=list(MICROCIRCUITS))
    ap.add_argument("--source", default=None, help="neurona iluminada (por defecto la del preset)")
    ap.add_argument("--theta", type=float, default=float(np.pi), help="ángulo del pulso láser (rad)")
    ap.add_argument("--gamma", type=float, default=1.0)
    ap.add_argument("--times", type=float, nargs="+", default=[10, 20, 30, 40])
    ap.add_argument("--mode", default="trotter", choices=["trotter", "givens"])
    ap.add_argument("--steps", type=int, default=2, help="pasos de Trotter (iguales para todos los tiempos)")
    ap.add_argument("--order", type=int, default=2, choices=[1, 2])
    ap.add_argument("--gateset", default="native", choices=["native", "qis"])
    ap.add_argument("--shots", type=int, default=1000)
    ap.add_argument("--dry-run", action="store_true", help="sólo muestra circuitos y recursos")
    ap.add_argument("--no-wait", action="store_true", help="envía y sale (consulta después con --refresh)")
    ap.add_argument("--refresh", nargs="*", help="ids de trabajos a actualizar")
    ap.add_argument("--yes", action="store_true", help="no pedir confirmación para QPU")
    return ap.parse_args()


def main() -> None:
    a = parse()
    m = MICROCIRCUITS[a.preset]
    names = list(m.neurons)
    source = a.source or m.default_source
    C = get_connectome()
    J = C.sub_coupling(names)
    src = [names.index(source)]

    print(f"\nMicrocircuito {m.name}: {', '.join(names)}  ·  láser en {source}, θ = {a.theta:.3f}")
    total_2q = 0
    for t in a.times:
        logical = build_microcircuit(J, src, a.theta, t, a.gamma, a.mode, a.steps, a.order, labels=names)
        comp = compile_native(logical) if a.gateset == "native" else lower_to_qis(logical)
        n2 = comp.n_two_qubit
        total_2q += n2
        print(f"  t = {t:6.2f}  →  {comp.counts()}   F_hw≈{hardware_fidelity(n2, comp.n_one_qubit):.2f}")
        if a.dry_run and t == a.times[0]:
            print(json.dumps(to_ionq_input(comp))[:800] + " …")
    print(f"  Total compuertas de 2 qubits en el experimento: {total_2q} × {a.shots} disparos")
    if a.dry_run:
        return

    try:
        client = IonQClient()
    except Exception as exc:
        sys.exit(f"\n{exc}")
    if a.refresh is not None:
        for jid in a.refresh:
            r = experiment.refresh_record(client, jid)
            print(jid, r["status"], json.dumps(r.get("analysis"), default=float)[:300])
        return

    if a.backend in QPU_BACKENDS and not a.yes:
        ans = input(f"\n¿Enviar {len(a.times)} trabajos a {a.backend}? Esto tiene costo. [s/N] ")
        if ans.strip().lower() not in {"s", "si", "sí", "y", "yes"}:
            sys.exit("Cancelado.")

    print("\nCalibrando orden de bits en el simulador ideal…")
    little = experiment.endianness_check(client)
    print("  qubit 0 = bit menos significativo" if little else "  ¡orden invertido! se corregirá")

    records = []
    for t in a.times:
        r = experiment.submit_microcircuit(
            client, backend=a.backend, noise_model=a.noise, shots=a.shots, gateset=a.gateset,
            preset=a.preset, sources=[source], theta=a.theta, t=t, gamma=a.gamma, mode=a.mode,
            steps=a.steps, order=a.order, little_endian=little,
        )
        print(f"  enviado t={t:g}: {r['job_id']}")
        records.append(r)
    if a.no_wait:
        print("\nConsulta luego con:  python scripts/run_ionq_experiment.py --refresh " +
              " ".join(r["job_id"] for r in records))
        return

    print("\nEsperando resultados…")
    print(f"{'t':>6} | {'TVD bruto':>9} | {'TVD post-sel.':>13} | {'aceptados':>9} | poblaciones post-seleccionadas")
    for r in records:
        client.wait(r["job_id"], timeout_s=6 * 3600)
        r = experiment.refresh_record(client, r["job_id"])
        an = r["analysis"]
        pops = " ".join(f"{nm}:{p:.2f}" for nm, p in zip(names, an["marginals_postselected"]))
        print(f"{r['params']['t']:6.1f} | {an['tvd_raw']:9.3f} | {an['tvd_postselected']:13.3f} | "
              f"{an['accepted_fraction']:9.2f} | {pops}")
    print(f"\nRegistros guardados en {experiment.JOBS_DIR}")


if __name__ == "__main__":
    main()
