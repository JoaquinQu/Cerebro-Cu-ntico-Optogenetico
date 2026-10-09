"""Escritor mínimo de glTF 2.0 binario (.glb) sin dependencias.

Convención compartida con Blender y el frontend (ver docs/MODELO_3D.md):
    1 unidad glTF = 100 µm  (GLTF_SCALE = 0.01)
    glTF (X, Y, Z) = (x_izq-der, z_dorsoventral, −y_anteroposterior) · GLTF_SCALE
Es exactamente lo que produce el exportador de Blender (+Y arriba) si en Blender se
usa X = x, Y = y, Z = z con la misma escala; por eso un modelo editado en Blender
puede reemplazar al generado aquí sin tocar el código.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

GLTF_SCALE = 0.01


def data_to_gltf(V: np.ndarray) -> np.ndarray:
    x, y, z = V[:, 0], V[:, 1], V[:, 2]
    return (np.stack([x, z, -y], axis=1) * GLTF_SCALE).astype(np.float32)


def write_glb(path: str | Path, meshes: list[dict], extras: dict | None = None) -> Path:
    """meshes: [{name, positions (N,3) f32, normals (N,3) f32, indices (M,3) u32, color [r,g,b,a]}]"""
    blob = bytearray()
    views, accessors, gl_meshes, nodes, materials = [], [], [], [], []

    def add_view(arr: np.ndarray, target: int) -> int:
        while len(blob) % 4:
            blob.append(0)
        off = len(blob)
        data = arr.tobytes()
        blob.extend(data)
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(data), "target": target})
        return len(views) - 1

    for i, m in enumerate(meshes):
        P = np.ascontiguousarray(m["positions"], dtype=np.float32)
        N = np.ascontiguousarray(m["normals"], dtype=np.float32)
        I = np.ascontiguousarray(m["indices"], dtype=np.uint32).reshape(-1)
        vp = add_view(P, 34962)
        vn = add_view(N, 34962)
        vi = add_view(I, 34963)
        accessors += [
            {"bufferView": vp, "componentType": 5126, "count": len(P), "type": "VEC3",
             "min": P.min(0).tolist(), "max": P.max(0).tolist()},
            {"bufferView": vn, "componentType": 5126, "count": len(N), "type": "VEC3"},
            {"bufferView": vi, "componentType": 5125, "count": len(I), "type": "SCALAR"},
        ]
        a = 3 * i
        materials.append({"name": m["name"], "pbrMetallicRoughness": {
            "baseColorFactor": m.get("color", [0.2, 0.5, 1.0, 0.3]), "metallicFactor": 0.0, "roughnessFactor": 0.4},
            "alphaMode": "BLEND", "doubleSided": True})
        gl_meshes.append({"name": m["name"], "primitives": [{
            "attributes": {"POSITION": a, "NORMAL": a + 1}, "indices": a + 2, "material": i, "mode": 4}]})
        nodes.append({"name": m["name"], "mesh": i})

    gltf = {
        "asset": {"version": "2.0", "generator": "cerebro-cuantico anatomy.py"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes))), "extras": extras or {}}],
        "nodes": nodes,
        "meshes": gl_meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(blob)}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    while len(blob) % 4:
        blob.append(0)
    total = 12 + 8 + len(js) + 8 + len(blob)
    out = struct.pack("<III", 0x46546C67, 2, total)
    out += struct.pack("<II", len(js), 0x4E4F534A) + js
    out += struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)
    return path
