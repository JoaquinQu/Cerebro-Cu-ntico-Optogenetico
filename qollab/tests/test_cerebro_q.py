"""Pruebas del núcleo de Qollab (con Qiskit real si está instalado; si no, con la imitación de dev/)."""

import json
import math
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
try:
    import qiskit  # noqa: F401
    REAL = not getattr(qiskit, "SIMULADO", False)
except ImportError:
    sys.path.insert(0, str(RAIZ / "dev" / "qiskit_simulado"))
    REAL = False

import os

os.chdir(RAIZ)  # las rutas de datos son relativas a la raíz del proyecto, igual que en Qollab

import numpy as np

from cerebro_q import analisis, api, circuitos, fisica


def backend_de_prueba():
    if REAL:
        from qiskit.providers.basic_provider import BasicSimulator
        return BasicSimulator()
    from qiskit import BackendSimulado
    return BackendSimulado()


class TestFisica(unittest.TestCase):
    def test_normalizacion(self):
        J, nombres, _ = fisica.acoplamientos()
        self.assertEqual(len(nombres), 302)
        self.assertAlmostEqual(np.max(np.abs(np.linalg.eigvalsh(J))), 1.0, places=9)

    def test_walk_conserva_norma(self):
        w = json.loads(api.walk_json("AVM", 1.2, 1.0, 40.0, 9))
        P = np.array(w["prob"])
        self.assertTrue(np.allclose(P.sum(axis=1), math.sin(0.6) ** 2, atol=1e-3))

    def test_xy_igual_a_walk(self):
        J = fisica.sub_acoplamientos(["AVM", "ALML", "AVDL", "AVAL", "PVCL", "PLML"])
        exacta = fisica.distribucion_exacta(J, [0], 2.0, 17.0, 1.0)
        walk = fisica.probabilidades_walk(np.linalg.eigh(J), 0, np.array([17.0]), 2.0, 1.0)[0]
        self.assertTrue(np.allclose(fisica.marginales(exacta, 6), walk, atol=1e-9))


class TestCircuitos(unittest.TestCase):
    def test_trotter_converge(self):
        J = fisica.sub_acoplamientos(["AVM", "ALML", "AVDL", "AVAL", "PVCL", "PLML"])
        exacta = fisica.distribucion_exacta(J, [0], math.pi, 20.0, 1.0)
        errs = [analisis.tvd(exacta, circuitos.probabilidades_ideales(
            circuitos.operaciones(6, [0], math.pi, circuitos.saltos_trotter(J, 20.0, r)), 6)) for r in (2, 8)]
        self.assertLess(errs[1], errs[0])
        self.assertLess(errs[1], 0.02)

    def test_givens_exacto(self):
        J = fisica.sub_acoplamientos(["AVM", "ALML", "AVDL", "AVAL", "PVCL", "PLML"])
        lam, V = np.linalg.eigh(J)
        amp = V @ (np.exp(-1j * lam * 25.0) * V[0])
        ops = circuitos.operaciones(6, [0], math.pi, circuitos.saltos_givens(amp, 0))
        self.assertLess(analisis.tvd(fisica.distribucion_exacta(J, [0], math.pi, 25.0, 1.0),
                                     circuitos.probabilidades_ideales(ops, 6)), 1e-9)

    def test_postseleccion(self):
        p = np.full(16, 1 / 16)
        ps, ac = analisis.postseleccionar(p, 4, 1)
        self.assertAlmostEqual(ac, 5 / 16)
        self.assertAlmostEqual(ps.sum(), 1.0)

    def test_orden_de_bits_qiskit(self):
        # '010' en Qiskit = qubit 1 en 1  →  índice 2
        p = analisis.conteos_a_probs({"010": 10}, 3)
        self.assertEqual(int(np.argmax(p)), 2)
        self.assertEqual(analisis.marginales(p, 3), [0.0, 1.0, 0.0])


class TestApiQollab(unittest.TestCase):
    def test_simular(self):
        s = json.loads(api.simular_json(json.dumps({"preset": "toque-6", "t": 30})))
        self.assertEqual(s["n_qubits"], 6)
        self.assertLess(s["tvd_circuito"], 0.15)
        self.assertIn("ruido", s)

    def test_ejecutar_un_solo_job_varios_tiempos(self):
        r = json.loads(api.ejecutar_json(backend_de_prueba(), json.dumps(
            {"preset": "toque-6", "modo": "givens", "tiempos": [10, 20, 30], "shots": 4000})))
        self.assertEqual(len(r["resultados"]), 3)
        for fila in r["resultados"]:
            self.assertLess(fila["tvd_bruto"], 0.06)  # backend ideal: sólo ruido estadístico
            self.assertAlmostEqual(fila["fraccion_aceptada"], 1.0, places=6)

    def test_cuerpo_glb(self):
        import base64
        self.assertEqual(base64.b64decode(api.cuerpo_glb())[:4], b"glTF")

    def test_backend_info(self):
        info = json.loads(api.backend_json(backend_de_prueba()))
        self.assertFalse(info["ionq"])

        class FalsoIonQ:
            name = "ionq_qpu.forte-1"
        info = json.loads(api.backend_json(FalsoIonQ()))
        self.assertTrue(info["ionq"] and info["hardware"])


class TestReglasQollab(unittest.TestCase):
    """Lo que exige el runtime de Qollab para un proyecto JS / Qiskit."""

    SUBIR = ["index.html", "main.js", "main.css", "requirements.txt", "js", "cerebro_q", "data"]

    def archivos(self):
        out = []
        for nombre in self.SUBIR:
            p = RAIZ / nombre
            out += [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file() and "__pycache__" not in f.parts]
        return out

    def test_limites(self):
        fs = self.archivos()
        self.assertLessEqual(len(fs), 100)
        for f in fs:
            self.assertLessEqual(f.stat().st_size, 2 * 1024 * 1024, f.name)

    def test_index_solo_cuerpo(self):
        html = (RAIZ / "index.html").read_text(encoding="utf-8").lower()
        import re
        for etiqueta in ("script", "html", "head", "body", "link", "style"):
            self.assertNotRegex(html, rf"<{etiqueta}[\s>]")
        self.assertIn("this effort is supported by qollab &amp; ionq.", html)

    def test_imports_de_js(self):
        import re
        for f in [RAIZ / "main.js", *(RAIZ / "js").glob("*.js")]:
            for spec in re.findall(r"from\s+[\"']([^\"']+)[\"']", f.read_text(encoding="utf-8")):
                ok = spec.startswith("./") or spec.startswith("../") or spec in ("three", "cerebro_q.api") \
                    or spec.startswith("three/addons/")
                self.assertTrue(ok, f"{f.name}: import no permitido en Qollab: {spec}")
            self.assertNotIn("localStorage", f.read_text(encoding="utf-8"), f.name)

    def test_rutas_literales_y_sin_secretos(self):
        from cerebro_q import datos
        for ruta in (datos.RUTA_NEURONAS, datos.RUTA_SINAPSIS, datos.RUTA_CUERPO):
            self.assertTrue((RAIZ / ruta).is_file(), ruta)
            self.assertIn(f'"{ruta}"', (RAIZ / "cerebro_q" / "datos.py").read_text(encoding="utf-8"))
        for f in self.archivos():
            if f.suffix in (".py", ".js", ".html", ".css", ".txt"):
                texto = f.read_text(encoding="utf-8")
                self.assertNotRegex(texto, r"(?i)(api[_-]?key|apikey)\s*[:=]\s*[\"'][A-Za-z0-9]{16,}", f.name)


if __name__ == "__main__":
    unittest.main()
