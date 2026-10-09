"""Modelo 3D: la malla anatómica contiene a las neuronas y el .glb es glTF 2.0 válido."""

import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from _helpers import random_graph  # noqa: F401
from cerebro.anatomy import build_worm, centerline
from cerebro.connectome import get_connectome
from cerebro.gltf import GLTF_SCALE, data_to_gltf, write_glb


class TestAnatomia(unittest.TestCase):
    def test_neuronas_dentro_del_cuerpo(self):
        pos = get_connectome().positions
        worm = build_worm(pos)
        V = worm["cuerpo"][0]
        ys, C, _ = centerline(pos)
        R = np.linalg.norm(V.reshape(len(ys), -1, 3) - C[:, None, :], axis=2).mean(axis=1)
        fuera = sum(np.hypot(p[0] - C[i, 0], p[2] - C[i, 2]) > R[i]
                    for p in pos for i in [int(np.argmin(np.abs(ys - p[1])))])
        self.assertLessEqual(fuera, 3)


class TestGLB(unittest.TestCase):
    def test_estructura_y_convencion(self):
        V = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 10.0]], dtype=np.float32)
        G = data_to_gltf(V)
        # glTF (X, Y, Z) = (x, z, −y)·escala  ⇒  datos = (X, −Z, Y)/escala
        back = np.stack([G[:, 0], -G[:, 2], G[:, 1]], axis=1) / GLTF_SCALE
        self.assertTrue(np.allclose(back, V, atol=1e-4))
        with tempfile.TemporaryDirectory() as d:
            p = write_glb(Path(d) / "t.glb", [{"name": "cuerpo", "positions": G,
                                                "normals": np.tile([0, 1, 0], (3, 1)).astype(np.float32),
                                                "indices": np.array([[0, 1, 2]], dtype=np.uint32)}])
            raw = p.read_bytes()
        magic, version, total = struct.unpack("<III", raw[:12])
        self.assertEqual((magic, version, total), (0x46546C67, 2, len(raw)))
        jlen, jtype = struct.unpack("<II", raw[12:20])
        self.assertEqual(jtype, 0x4E4F534A)
        gltf = json.loads(raw[20:20 + jlen])
        self.assertEqual(gltf["asset"]["version"], "2.0")
        self.assertEqual(gltf["accessors"][0]["count"], 3)
        self.assertEqual(len(raw) % 4, 0)


if __name__ == "__main__":
    unittest.main()
