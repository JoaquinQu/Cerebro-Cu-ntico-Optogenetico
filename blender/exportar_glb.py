"""Exporta los objetos 'Cuerpo' y 'Faringe' del .blend abierto a glTF para la app.

    blender --background blender/escena_gusano.blend --python blender/exportar_glb.py -- frontend/assets/gusano.glb

No modifica la escena: sirve para llevar a la app un cuerpo retocado a mano en Blender.
"""

import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ruta = args[0] if args else "frontend/assets/gusano.glb"
objetos = [o for o in bpy.data.objects if o.type == "MESH" and o.name.split(".")[0] in ("Cuerpo", "Faringe")]
if not objetos:
    raise SystemExit("No hay objetos 'Cuerpo' ni 'Faringe' en este .blend")
bpy.ops.object.select_all(action="DESELECT")
for o in objetos:
    o.select_set(True)
bpy.context.view_layer.objects.active = objetos[0]
bpy.ops.export_scene.gltf(filepath=ruta, export_format="GLB", use_selection=True, export_yup=True, export_apply=True)
print(f"glTF exportado en {ruta} ({', '.join(o.name for o in objetos)})")
