"""Genera frontend/assets/gusano.glb: cuerpo anatómico + faringe a partir de los datos.

    python scripts/generar_modelo_3d.py

El .glb se puede abrir en Blender (File → Import → glTF), editar y volver a exportar
sobre el mismo archivo con "+Y Up"; la app lo carga automáticamente (docs/MODELO_3D.md).
"""

import _path  # noqa: F401
import numpy as np

from cerebro.anatomy import build_worm
from cerebro.config import FRONTEND_DIR
from cerebro.connectome import load_neurons
from cerebro.gltf import GLTF_SCALE, data_to_gltf, write_glb


def main() -> None:
    neurons = load_neurons()
    pos = np.array([[d["x"], d["y"], d["z"]] for d in neurons])
    worm = build_worm(pos)
    meshes = []
    for name, color in (("cuerpo", [0.16, 0.43, 1.0, 0.25]), ("faringe", [0.5, 0.85, 1.0, 0.35])):
        V, F, N = worm[name]
        Vg = data_to_gltf(V)
        Ng = data_to_gltf(N) / GLTF_SCALE
        meshes.append({"name": name, "positions": Vg, "normals": Ng, "indices": F, "color": color})
    out = write_glb(FRONTEND_DIR / "assets" / "gusano.glb", meshes,
                    extras={"escala_um_por_unidad": 1 / GLTF_SCALE, **worm["info"]})
    print(f"Escrito {out}  ({out.stat().st_size / 1024:.0f} KB) · {worm['info']}")


if __name__ == "__main__":
    main()
