"""Exporta los datos de la escena para Blender (blender/datos_escena.json).

    python scripts/exportar_blender.py                       # láser en AVM, θ = π
    python scripts/exportar_blender.py --fuente PLML --tmax 80 --cuadros 160

Incluye: neuronas (posición µm, tipo), sinapsis más fuertes, la malla anatómica
(cuerpo + faringe, la misma que usa la app) y P_k(t) del quantum walk exacto.
Luego:  blender --background --python ../blender/animar_gusano.py -- --render
"""

import argparse
import json
import math

import _path  # noqa: F401
import numpy as np

from cerebro.anatomy import build_worm
from cerebro.config import PROJECT_DIR
from cerebro.connectome import get_connectome
from cerebro.hamiltonian import firing_probabilities


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fuente", default="AVM", help="neurona iluminada por el láser")
    ap.add_argument("--theta", type=float, default=math.pi)
    ap.add_argument("--gamma", type=float, default=1.0)
    ap.add_argument("--tmax", type=float, default=60.0)
    ap.add_argument("--cuadros", type=int, default=120, help="instantes de tiempo del walk")
    ap.add_argument("--aristas", type=int, default=800, help="sinapsis más fuertes a dibujar")
    ap.add_argument("--salida", default=str(PROJECT_DIR / "blender" / "datos_escena.json"))
    a = ap.parse_args()

    C = get_connectome()
    j = C.index(a.fuente)
    times = np.linspace(0, a.tmax, a.cuadros)
    P = firing_probabilities(C.eigh(), j, times, a.theta, a.gamma)
    worm = build_worm(C.positions)
    edges = sorted(C.edge_list(), key=lambda e: -e[2])[: a.aristas]

    def mesh(name):
        V, F, _ = worm[name]
        return {"v": np.round(V, 2).reshape(-1).tolist(), "f": F.reshape(-1).tolist()}

    data = {
        "meta": {"fuente": a.fuente, "indice_fuente": j, "theta": a.theta, "gamma": a.gamma,
                 "p_disparo": math.sin(a.theta / 2) ** 2, "unidades": "µm (x izq-der, y anteroposterior, z dorsoventral)",
                 "datos": "Cook et al. 2019 vía OpenWorm; posiciones OpenWorm CElegansNeuroML"},
        "neuronas": [{"nombre": nm, "x": float(p[0]), "y": float(p[1]), "z": float(p[2]), "tipo": tp}
                     for nm, p, tp in zip(C.names, C.positions, C.types)],
        "aristas": [[i, k, round(w, 5)] for i, k, w in edges],
        "walk": {"tiempos": times.round(4).tolist(), "prob": np.round(P, 5).tolist()},
        "cuerpo": mesh("cuerpo"),
        "faringe": mesh("faringe"),
    }
    with open(a.salida, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(f"Escrito {a.salida} · láser en {a.fuente} · {a.cuadros} instantes · {len(edges)} sinapsis")


if __name__ == "__main__":
    main()
