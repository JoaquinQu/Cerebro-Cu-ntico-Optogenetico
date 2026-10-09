"""Escena cinematográfica de Cerebro Cuántico Optogenético para Blender (4.2 LTS o superior).

Construye el gusano C. elegans con sus 302 neuronas en posiciones reales, las sinapsis,
el cuerpo anatómico, el haz del láser y una cámara animada, y anima el brillo de cada
neurona con P_k(t) del quantum walk exacto (datos exportados por el backend).

Uso (desde la carpeta del proyecto):

    # 1) exportar los datos (una vez, o cada vez que cambies la neurona fuente)
    python backend/scripts/exportar_blender.py --fuente AVM

    # 2a) abrir la escena en Blender para revisarla/ajustarla
    blender --python blender/animar_gusano.py

    # 2b) o renderizar directo el video (sin abrir la interfaz)
    blender --background --python blender/animar_gusano.py -- --render
    blender --background --python blender/animar_gusano.py -- --render --motor cycles --calidad alta

Opciones (después de "--"):
    --datos RUTA          JSON exportado (por defecto blender/datos_escena.json)
    --motor eevee|cycles  motor de render (por defecto eevee: rápido)
    --calidad borrador|media|alta   resolución y muestras (por defecto media = 1920×1080)
    --render              renderiza la animación a blender/render/
    --guardar RUTA        guarda el .blend (por defecto blender/escena_gusano.blend)
    --exportar-glb RUTA   exporta cuerpo + faringe a glTF para la app (frontend/assets/gusano.glb)

Convención de coordenadas (igual que la app, docs/MODELO_3D.md):
    Blender X = x (izq–der), Y = y (anteroposterior), Z = z (dorsoventral), 1 unidad = 100 µm.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

try:
    import bpy
    import bmesh
except ImportError:  # permite importar las funciones puras fuera de Blender (tests)
    bpy = None
    bmesh = None

ESCALA = 0.01  # unidades de Blender por µm (1 BU = 100 µm)
FPS = 30
CUADROS_LASER = 40  # duración del disparo del láser (cuadros)
CUADROS_WALK = 330  # duración de la propagación (cuadros)

AQUI = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd() / "blender"

COLOR_TIPO = {
    "sensory": (0.18, 0.83, 0.75),
    "interneuron": (0.65, 0.55, 0.98),
    "motor": (0.96, 0.62, 0.04),
    "unknown": (0.58, 0.64, 0.72),
}
PALETA = [(0.0, (0.07, 0.13, 0.29)), (0.35, (0.12, 0.42, 1.0)), (0.7, (0.22, 0.88, 1.0)), (1.0, (1.0, 1.0, 1.0))]
CALIDADES = {
    "borrador": {"res": (960, 540), "eevee": 16, "cycles": 24},
    "media": {"res": (1920, 1080), "eevee": 32, "cycles": 64},
    "alta": {"res": (1920, 1080), "eevee": 64, "cycles": 256},
}


# ---------------------------------------------------------------------------
# Utilidades puras (sin bpy)
# ---------------------------------------------------------------------------
def leer_argumentos(argv: list[str]) -> dict:
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    op = {"datos": str(AQUI / "datos_escena.json"), "motor": "eevee", "calidad": "media", "render": False,
          "guardar": str(AQUI / "escena_gusano.blend"), "exportar_glb": None}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--render":
            op["render"] = True
        elif a in ("--datos", "--motor", "--calidad", "--guardar", "--exportar-glb"):
            op[a[2:].replace("-", "_")] = args[i + 1]
            i += 1
        i += 1
    return op


def actividad_relativa(prob_t: list[float]) -> list[float]:
    """Brillo por neurona en un instante: P/max(P) con un leve realce (igual que la app)."""
    m = max(max(prob_t), 1e-12)
    return [min(1.0, (p / m) ** 0.8) for p in prob_t]


def cuadro_de_indice(k: int, total: int) -> int:
    """Cuadro de video para el instante k del walk (después del láser)."""
    return 1 + CUADROS_LASER + round(k * CUADROS_WALK / max(total - 1, 1))


def a_blender(x: float, y: float, z: float) -> tuple[float, float, float]:
    return (x * ESCALA, y * ESCALA, z * ESCALA)


# ---------------------------------------------------------------------------
# Compatibilidad entre versiones de Blender
# ---------------------------------------------------------------------------
def elegir_motor(sc, nombre: str) -> str:
    """Asigna el motor probando los identificadores de cada versión (EEVEE cambió de nombre en 4.2)."""
    candidatos = ["CYCLES"] if nombre == "cycles" else ["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"]
    for cand in candidatos:
        try:
            sc.render.engine = cand
            return cand
        except TypeError:
            continue
    return sc.render.engine


def socket(coleccion, identificador: str, respaldo: int):
    """Busca un socket por identificador (estable entre versiones) o por posición."""
    for s in coleccion:
        if getattr(s, "identifier", None) == identificador:
            return s
    return coleccion[respaldo]


def material_transparente(mat) -> None:
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(mat, attr, val)
            return
        except (AttributeError, TypeError):
            continue


def nuevo_material(nombre: str):
    mat = bpy.data.materials.new(nombre)
    try:
        mat.use_nodes = True  # en Blender 5 ya es siempre verdadero
    except AttributeError:
        pass
    mat.node_tree.nodes.clear()
    return mat


def malla_icosfera(nombre: str, radio: float):
    me = bpy.data.meshes.new(nombre)
    bm = bmesh.new()
    try:
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=radio)
    except TypeError:
        bmesh.ops.create_icosphere(bm, subdivisions=2, diameter=radio)
    bm.to_mesh(me)
    bm.free()
    suavizar(me)
    return me


def malla_cono(nombre: str, r1: float, r2: float, largo: float, segmentos: int = 32):
    me = bpy.data.meshes.new(nombre)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, cap_tris=False, segments=segmentos, radius1=r1, radius2=r2, depth=largo)
    bm.to_mesh(me)
    bm.free()
    suavizar(me)
    return me


def suavizar(me) -> None:
    try:
        me.shade_smooth()
    except AttributeError:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))


def enlazar(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


# ---------------------------------------------------------------------------
# Materiales
# ---------------------------------------------------------------------------
def material_neurona():
    """Emisión controlada por propiedades del objeto: 'actividad' (0–1) y 'color_tipo'."""
    mat = nuevo_material("Neurona")
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    out = N.new("ShaderNodeOutputMaterial")
    emi = N.new("ShaderNodeEmission")
    act = N.new("ShaderNodeAttribute")
    act.attribute_type = "OBJECT"
    act.attribute_name = "actividad"
    tipo = N.new("ShaderNodeAttribute")
    tipo.attribute_type = "OBJECT"
    tipo.attribute_name = "color_tipo"
    ramp = N.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = PALETA[0][0], (*PALETA[0][1], 1)
    els[1].position, els[1].color = PALETA[-1][0], (*PALETA[-1][1], 1)
    for pos, col in PALETA[1:-1]:
        e = els.new(pos)
        e.color = (*col, 1)
    # mezcla: color del tipo (atenuado) cuando está en reposo → mapa de colores cuando se activa
    L.new(act.outputs["Fac"], ramp.inputs["Fac"])
    mezcla_f = N.new("ShaderNodeMath")
    mezcla_f.operation = "MULTIPLY"
    mezcla_f.use_clamp = True
    mezcla_f.inputs[1].default_value = 6.0
    L.new(act.outputs["Fac"], mezcla_f.inputs[0])
    mix = N.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    L.new(mezcla_f.outputs[0], socket(mix.inputs, "Factor_Float", 0))
    tipo_dim = N.new("ShaderNodeMix")  # color_tipo × 0.35
    tipo_dim.data_type = "RGBA"
    tipo_dim.blend_type = "MULTIPLY"
    socket(tipo_dim.inputs, "Factor_Float", 0).default_value = 1.0
    L.new(tipo.outputs["Color"], socket(tipo_dim.inputs, "A_Color", 6))
    socket(tipo_dim.inputs, "B_Color", 7).default_value = (0.35, 0.35, 0.35, 1)
    L.new(socket(tipo_dim.outputs, "Result_Color", 2), socket(mix.inputs, "A_Color", 6))
    L.new(ramp.outputs["Color"], socket(mix.inputs, "B_Color", 7))
    L.new(socket(mix.outputs, "Result_Color", 2), emi.inputs["Color"])
    # intensidad: 1.5 en reposo → 1.5 + 30·actividad
    fuerza = N.new("ShaderNodeMath")
    fuerza.operation = "MULTIPLY_ADD"
    fuerza.inputs[1].default_value = 30.0
    fuerza.inputs[2].default_value = 1.5
    L.new(act.outputs["Fac"], fuerza.inputs[0])
    L.new(fuerza.outputs[0], emi.inputs["Strength"])
    L.new(emi.outputs[0], out.inputs["Surface"])
    return mat


def material_emisivo(nombre: str, color, fuerza: float):
    mat = nuevo_material(nombre)
    N = mat.node_tree.nodes
    out = N.new("ShaderNodeOutputMaterial")
    emi = N.new("ShaderNodeEmission")
    emi.inputs["Color"].default_value = (*color, 1)
    emi.inputs["Strength"].default_value = fuerza
    mat.node_tree.links.new(emi.outputs[0], out.inputs["Surface"])
    return mat, emi


def material_piel(nombre: str, color_borde, fuerza: float, opacidad: float):
    """Cutícula translúcida: brillo de borde (Fresnel/facing) sobre fondo transparente."""
    mat = nuevo_material(nombre)
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    out = N.new("ShaderNodeOutputMaterial")
    lw = N.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    curva = N.new("ShaderNodeMath")
    curva.operation = "POWER"
    curva.inputs[1].default_value = 2.2
    L.new(lw.outputs["Facing"], curva.inputs[0])
    emi = N.new("ShaderNodeEmission")
    emi.inputs["Color"].default_value = (*color_borde, 1)
    emi.inputs["Strength"].default_value = fuerza
    tr = N.new("ShaderNodeBsdfTransparent")
    fac = N.new("ShaderNodeMath")
    fac.operation = "MULTIPLY"
    fac.use_clamp = True
    fac.inputs[1].default_value = opacidad
    L.new(curva.outputs[0], fac.inputs[0])
    mix = N.new("ShaderNodeMixShader")
    L.new(fac.outputs[0], mix.inputs["Fac"])
    L.new(tr.outputs[0], mix.inputs[1])
    L.new(emi.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], out.inputs["Surface"])
    material_transparente(mat)
    return mat


# ---------------------------------------------------------------------------
# Construcción de la escena
# ---------------------------------------------------------------------------
def limpiar_escena():
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    except RuntimeError:  # p.ej. si se ejecuta desde el editor de texto
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
    sc = bpy.context.scene
    sc.name = "CerebroCuantico"
    return sc


def crear_mundo(sc):
    w = bpy.data.worlds.new("Fondo")
    sc.world = w
    w.color = (0.004, 0.006, 0.014)
    try:
        w.use_nodes = True
        bg = w.node_tree.nodes.get("Background") or w.node_tree.nodes.new("ShaderNodeBackground")
        bg.inputs["Color"].default_value = (0.004, 0.006, 0.014, 1)
        bg.inputs["Strength"].default_value = 1.0
    except Exception as exc:  # pragma: no cover
        print("[aviso] mundo sin nodos:", exc)


def crear_malla_de_datos(nombre: str, datos: dict, material):
    v = datos["v"]
    f = datos["f"]
    verts = [a_blender(v[i], v[i + 1], v[i + 2]) for i in range(0, len(v), 3)]
    caras = [(f[i], f[i + 1], f[i + 2]) for i in range(0, len(f), 3)]
    me = bpy.data.meshes.new(nombre)
    me.from_pydata(verts, [], caras)
    me.update()
    suavizar(me)
    me.materials.append(material)
    return enlazar(bpy.data.objects.new(nombre, me))


def crear_neuronas(datos: dict):
    malla = malla_icosfera("Soma", 3.2 * ESCALA)
    mat = material_neurona()
    malla.materials.append(mat)
    col = bpy.data.collections.new("Neuronas")
    bpy.context.scene.collection.children.link(col)
    objetos = []
    for d in datos["neuronas"]:
        o = bpy.data.objects.new(d["nombre"], malla)
        o.location = a_blender(d["x"], d["y"], d["z"])
        o["actividad"] = 0.0
        o["color_tipo"] = COLOR_TIPO.get(d["tipo"], COLOR_TIPO["unknown"])
        col.objects.link(o)
        # el tamaño crece con la actividad (driver simple, sin Python)
        for eje in range(3):
            fc = o.driver_add("scale", eje)
            drv = fc.driver
            drv.type = "SCRIPTED"
            var = drv.variables.new()
            var.name = "a"
            var.type = "SINGLE_PROP"
            var.targets[0].id = o
            var.targets[0].data_path = '["actividad"]'
            drv.expression = "1 + 1.6*a"
        objetos.append(o)
    return objetos


def crear_sinapsis(datos: dict):
    cu = bpy.data.curves.new("Sinapsis", type="CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.25 * ESCALA
    cu.bevel_resolution = 1
    pos = [a_blender(d["x"], d["y"], d["z"]) for d in datos["neuronas"]]
    for i, j, _w in datos["aristas"]:
        sp = cu.splines.new("POLY")
        sp.points.add(1)
        sp.points[0].co = (*pos[i], 1)
        sp.points[1].co = (*pos[j], 1)
    mat, _ = material_emisivo("Sinapsis", (0.16, 0.36, 0.95), 0.6)
    cu.materials.append(mat)
    return enlazar(bpy.data.objects.new("Sinapsis", cu))


def animar_actividad(neuronas, datos: dict):
    prob = datos["walk"]["prob"]
    T = len(prob)
    prefs = bpy.context.preferences.edit
    interp_original = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = "LINEAR"
    try:
        for o in neuronas:  # reposo durante el láser
            o["actividad"] = 0.0
            o.keyframe_insert('["actividad"]', frame=1)
        for k in range(T):
            act = actividad_relativa(prob[k])
            f = cuadro_de_indice(k, T)
            for o, a in zip(neuronas, act):
                o["actividad"] = a
                o.keyframe_insert('["actividad"]', frame=f)
    finally:
        prefs.keyframe_new_interpolation_type = interp_original


def crear_laser(datos: dict):
    fuente = datos["neuronas"][datos["meta"]["indice_fuente"]]
    p = a_blender(fuente["x"], fuente["y"], fuente["z"])
    largo = 3.0
    origen = (p[0] + 0.4, p[1] - 0.3, p[2] + largo)
    import mathutils

    v = mathutils.Vector(p) - mathutils.Vector(origen)
    rot = v.to_track_quat("-Z", "Y").to_euler()
    centro = (mathutils.Vector(origen) + mathutils.Vector(p)) / 2

    mat_haz, emi_haz = material_emisivo("Laser", (0.30, 0.64, 1.0), 0.0)
    haz = enlazar(bpy.data.objects.new("Laser", malla_cono("Haz", 0.012, 0.05, v.length)))
    haz.data.materials.append(mat_haz)
    haz.location, haz.rotation_euler = centro, rot
    mat_nucleo, emi_nucleo = material_emisivo("LaserNucleo", (0.9, 0.96, 1.0), 0.0)
    nucleo = enlazar(bpy.data.objects.new("LaserNucleo", malla_cono("Nucleo", 0.004, 0.008, v.length)))
    nucleo.data.materials.append(mat_nucleo)
    nucleo.location, nucleo.rotation_euler = centro, rot

    mat_anillo, emi_anillo = material_emisivo("Onda", (0.30, 0.64, 1.0), 0.0)
    anillo = enlazar(bpy.data.objects.new("Onda", malla_cono("Anillo", 0.08, 0.08, 0.004, 64)))
    anillo.data.materials.append(mat_anillo)
    anillo.location = p
    anillo.rotation_euler = (0.0, math.pi / 2, 0.0)  # de frente a la cámara lateral

    luz = bpy.data.lights.new("Destello", type="POINT")
    luz.color = (0.45, 0.7, 1.0)
    luz.shadow_soft_size = 0.05
    destello = enlazar(bpy.data.objects.new("Destello", luz))
    destello.location = p

    claves = [(1, 0.0), (6, 1.0), (CUADROS_LASER - 8, 1.0), (CUADROS_LASER + 6, 0.0)]
    for f, k in claves:
        emi_haz.inputs["Strength"].default_value = 18 * k
        emi_haz.inputs["Strength"].keyframe_insert("default_value", frame=f)
        emi_nucleo.inputs["Strength"].default_value = 60 * k
        emi_nucleo.inputs["Strength"].keyframe_insert("default_value", frame=f)
        luz.energy = 40 * k
        luz.keyframe_insert("energy", frame=f)
    for f, s, e in [(4, 0.3, 40.0), (CUADROS_LASER + 20, 9.0, 0.0)]:
        anillo.scale = (s, s, 1)
        anillo.keyframe_insert("scale", frame=f)
        emi_anillo.inputs["Strength"].default_value = e
        emi_anillo.inputs["Strength"].keyframe_insert("default_value", frame=f)
    return p


def crear_camara(sc, foco, centro, largo_cuerpo):
    pivote = enlazar(bpy.data.objects.new("Pivote", None))
    cam_data = bpy.data.cameras.new("Camara")
    cam_data.lens = 50
    cam_data.clip_start = 0.01
    cam_data.clip_end = 200
    cam = enlazar(bpy.data.objects.new("Camara", cam_data))
    cam.parent = pivote
    sc.camera = cam
    rastreo = cam.constraints.new("TRACK_TO")
    rastreo.target = pivote
    rastreo.track_axis = "TRACK_NEGATIVE_Z"
    rastreo.up_axis = "UP_Y"

    fin = CUADROS_LASER + CUADROS_WALK + 30
    # 1) primer plano del láser  2) se aleja mientras la excitación se propaga  3) giro lento
    claves = [
        (1, foco, (2.2, 0.0, 0.9), 0.0),
        (CUADROS_LASER + 15, foco, (2.4, 0.0, 1.0), 0.0),
        (CUADROS_LASER + 150, centro, (largo_cuerpo * 1.6, 0.0, largo_cuerpo * 0.4), math.radians(-12)),
        (fin, centro, (largo_cuerpo * 1.5, 0.0, largo_cuerpo * 0.5), math.radians(18)),
    ]
    for f, pos, off, giro in claves:
        pivote.location = pos
        pivote.rotation_euler = (0, 0, giro)
        cam.location = off
        pivote.keyframe_insert("location", frame=f)
        pivote.keyframe_insert("rotation_euler", frame=f)
        cam.keyframe_insert("location", frame=f)
    try:
        cam_data.dof.use_dof = True
        cam_data.dof.focus_object = pivote
        cam_data.dof.aperture_fstop = 4.0
    except AttributeError:
        pass
    return fin


def crear_rotulo(sc, cam, datos: dict):
    """Texto pequeño anclado a la cámara con el tiempo de la simulación."""
    txt = bpy.data.curves.new("Rotulo", type="FONT")
    txt.size = 0.035
    txt.body = ""
    obj = enlazar(bpy.data.objects.new("Rotulo", txt))
    obj.parent = cam
    obj.location = (-0.33, -0.17, -1.0)
    mat, _ = material_emisivo("Texto", (0.75, 0.85, 1.0), 1.5)
    txt.materials.append(mat)
    tiempos = datos["walk"]["tiempos"]
    fuente = datos["meta"]["fuente"]

    def actualizar(escena, *_):
        f = escena.frame_current
        if f <= CUADROS_LASER:
            txt.body = f"Laser optogenetico -> {fuente}"
        else:
            k = min(len(tiempos) - 1, max(0, round((f - 1 - CUADROS_LASER) * (len(tiempos) - 1) / CUADROS_WALK)))
            txt.body = f"t = {tiempos[k]:.1f}    P_k(t) = sin^2(θ/2) |<k| exp(-iγJt) |j>|^2"

    bpy.app.handlers.frame_change_pre.append(actualizar)
    actualizar(sc)


def configurar_render(sc, motor: str, calidad: str, fin: int):
    q = CALIDADES[calidad]
    elegir_motor(sc, motor)
    sc.render.use_lock_interface = True  # el rótulo se actualiza con un handler por cuadro
    sc.render.resolution_x, sc.render.resolution_y = q["res"]
    sc.render.resolution_percentage = 100
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, fin
    if sc.render.engine == "CYCLES":
        sc.cycles.samples = q["cycles"]
        try:
            sc.cycles.use_denoising = True
        except AttributeError:
            pass
    else:
        try:
            sc.eevee.taa_render_samples = q["eevee"]
        except AttributeError:
            pass
        if hasattr(sc.eevee, "use_bloom"):  # Blender ≤ 4.1
            sc.eevee.use_bloom = True
            sc.eevee.bloom_intensity = 0.08
    try:
        sc.view_settings.view_transform = "AgX"
    except TypeError:
        sc.view_settings.view_transform = "Filmic"
    configurar_brillo(sc)


def configurar_brillo(sc):
    """Resplandor (glare) en el compositor. API distinta en Blender 4.x y 5.x."""
    try:
        if bpy.app.version >= (5, 0, 0):
            tree = bpy.data.node_groups.new("Compositor", "CompositorNodeTree")
            sc.compositing_node_group = tree
            tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
            salida = tree.nodes.new("NodeGroupOutput").inputs[0]
        else:
            sc.use_nodes = True
            tree = sc.node_tree
            tree.nodes.clear()
            salida = tree.nodes.new("CompositorNodeComposite").inputs["Image"]
        capas = tree.nodes.new("CompositorNodeRLayers")
        try:
            capas.scene = sc
        except AttributeError:
            pass
        glare = tree.nodes.new("CompositorNodeGlare")
        ajustado = False
        for attr, val in (("glare_type", "BLOOM"), ("glare_type", "FOG_GLOW")):
            try:
                setattr(glare, attr, val)
                ajustado = True
                break
            except (AttributeError, TypeError):
                continue
        if not ajustado:  # Blender 5: opciones como entradas del nodo
            for nombre, val in (("Type", "Bloom"), ("Type", "Fog Glow")):
                try:
                    glare.inputs[nombre].default_value = val
                    break
                except (KeyError, TypeError, AttributeError):
                    continue
        for nombre, val in (("threshold", 0.8), ("size", 8)):
            try:
                setattr(glare, nombre, val)
            except (AttributeError, TypeError):
                try:
                    glare.inputs[nombre.capitalize()].default_value = val
                except (KeyError, TypeError, AttributeError):
                    pass
        tree.links.new(capas.outputs["Image"], glare.inputs[0])
        tree.links.new(glare.outputs[0], salida)
    except Exception as exc:  # pragma: no cover - el resplandor es opcional
        print(f"[aviso] no se pudo configurar el resplandor del compositor ({exc}); se renderiza sin él.")


def configurar_salida(sc, carpeta: Path):
    carpeta.mkdir(parents=True, exist_ok=True)
    img = sc.render.image_settings
    try:
        if hasattr(img, "media_type"):  # Blender 5
            img.media_type = "VIDEO"
        img.file_format = "FFMPEG"
        sc.render.ffmpeg.format = "MPEG4"
        sc.render.ffmpeg.codec = "H264"
        sc.render.ffmpeg.constant_rate_factor = "HIGH"
        sc.render.filepath = str(carpeta / "cerebro_cuantico.mp4")
    except (TypeError, AttributeError) as exc:
        print(f"[aviso] sin salida de video ({exc}); se guardan cuadros PNG.")
        if hasattr(img, "media_type"):
            img.media_type = "IMAGE"
        img.file_format = "PNG"
        sc.render.filepath = str(carpeta / "cuadro_")


def exportar_glb(ruta: str, objetos):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objetos:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objetos[0]
    bpy.ops.export_scene.gltf(filepath=ruta, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True)
    print(f"glTF exportado en {ruta}")


# ---------------------------------------------------------------------------
def main():
    op = leer_argumentos(sys.argv)
    ruta = Path(op["datos"])
    if not ruta.exists():
        raise SystemExit(f"No encuentro {ruta}. Corre primero: python backend/scripts/exportar_blender.py")
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    print(f"Datos: {len(datos['neuronas'])} neuronas · {len(datos['aristas'])} sinapsis · "
          f"{len(datos['walk']['prob'])} instantes · láser en {datos['meta']['fuente']}")

    sc = limpiar_escena()
    crear_mundo(sc)
    cuerpo = crear_malla_de_datos("Cuerpo", datos["cuerpo"], material_piel("Cuticula", (0.35, 0.75, 1.0), 2.0, 0.55))
    faringe = crear_malla_de_datos("Faringe", datos["faringe"], material_piel("Faringe", (0.55, 0.9, 1.0), 1.2, 0.35))
    neuronas = crear_neuronas(datos)
    crear_sinapsis(datos)
    print("Animando la actividad neuronal…")
    animar_actividad(neuronas, datos)
    foco = crear_laser(datos)

    ys = [d["y"] for d in datos["neuronas"]]
    xs = [d["x"] for d in datos["neuronas"]]
    zs = [d["z"] for d in datos["neuronas"]]
    centro = a_blender(sum(xs) / len(xs), (min(ys) + max(ys)) / 2, sum(zs) / len(zs))
    largo = (max(ys) - min(ys)) * ESCALA
    fin = crear_camara(sc, foco, centro, largo)
    crear_rotulo(sc, sc.camera, datos)
    configurar_render(sc, op["motor"], op["calidad"], fin)
    configurar_salida(sc, AQUI / "render")
    sc.frame_set(1)

    if op["exportar_glb"]:
        exportar_glb(op["exportar_glb"], [cuerpo, faringe])
    if op["guardar"]:
        bpy.ops.wm.save_as_mainfile(filepath=op["guardar"])
        print(f"Escena guardada en {op['guardar']}")
    if op["render"]:
        print(f"Renderizando {fin} cuadros con {sc.render.engine} ({op['calidad']})…")
        bpy.ops.render.render(animation=True)
        print(f"Listo: {sc.render.filepath}")


if __name__ == "__main__" and bpy is not None:
    main()
