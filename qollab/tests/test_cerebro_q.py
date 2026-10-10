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

from cerebro_q import analisis, api, cascada, circuitos, fisica


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

    def test_theta_escala_y_eje_fijo(self):
        """Con un láser θ sólo escala P_k por sin²(θ/2): el eje fijo (escala de θ = π) debe mostrarlo."""
        lleno = json.loads(api.simular_json(json.dumps({"preset": "toque-6", "t": 30, "theta": math.pi})))
        medio = json.loads(api.simular_json(json.dumps({"preset": "toque-6", "t": 30, "theta": math.pi / 2})))
        self.assertAlmostEqual(lleno["escala_y"], medio["escala_y"], places=5)
        self.assertEqual(lleno["pasos"], medio["pasos"])  # el autoajuste de Trotter no depende de θ
        for serie in ("exacta", "ideal"):
            np.testing.assert_allclose(np.array(medio[serie]), 0.5 * np.array(lleno[serie]), atol=1e-5)

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


class TestCascada(unittest.TestCase):
    """Quantum walk por ventanas (docs/PLAN_WALK_VENTANAS.md)."""

    def test_ventana(self):
        J, nombres, _ = fisica.acoplamientos()
        for nombre in ("AVM", "ASHL", "DA1"):
            c = fisica.indice(nombre)
            w = cascada.ventana(c)
            self.assertEqual(len(w), 10)
            self.assertEqual(w[0], c)
            self.assertEqual(len(set(w)), 10)
            self.assertEqual(w, cascada.ventana(c))  # determinista
            vecinas = set(np.nonzero(J[c])[0])
            for j in w[1:]:  # vecina directa, o a distancia 2 si faltan
                self.assertTrue(j in vecinas or any(J[v, j] > 0 for v in w[1:] if v in vecinas))

    def test_circuito_paso_igual_a_teoria(self):
        J, _, _ = fisica.acoplamientos()
        w = cascada.ventana(fisica.indice("AVM"))
        Js = J[np.ix_(w, w)]
        exacta = fisica.distribucion_exacta(Js, [0], math.pi, 5.0, 1.0)
        ops = cascada.operaciones_paso(Js, math.pi, 5.0, 1.0, 2)
        self.assertLess(analisis.tvd(exacta, circuitos.probabilidades_ideales(ops, 10)), 0.01)
        qc, metodo = cascada.circuito_paso(Js, math.pi, 5.0, 1.0, 2)
        if REAL:  # Qiskit real: PauliEvolutionGate + SuzukiTrotter debe dar lo mismo
            from qiskit.quantum_info import Statevector
            self.assertEqual(metodo, "pauli_evolution")
            sv = Statevector.from_instruction(qc.remove_final_measurements(inplace=False))
            self.assertLess(analisis.tvd(exacta, sv.probabilities()), 0.01)

    def test_paso_en_backend(self):
        r = json.loads(api.paso_json(backend_de_prueba(), json.dumps(
            {"centro": "AVM", "tau": 5, "shots": 400, "pasos_trotter": 2, "semilla": 3})))
        self.assertEqual(r["centro"], "AVM")
        self.assertEqual(len(r["ventana"]), 10)
        self.assertIn(r["spike"], r["ventana"])
        self.assertAlmostEqual(sum(r["medida"]), 1.0, places=6)
        self.assertAlmostEqual(r["fraccion_valida"], 1.0, places=6)  # backend ideal
        self.assertLess(0.5 * sum(abs(a - b) for a, b in zip(r["medida"], r["teoria_circuito"])), 0.15)

    def test_paso_sin_disparo(self):
        r = json.loads(api.paso_json(backend_de_prueba(), json.dumps(
            {"centro": "AVM", "tau": 5, "theta": 0.0, "shots": 50, "semilla": 1})))
        self.assertIsNone(r["spike"])
        self.assertEqual(r["motivo_fin"], "vacio")

    def test_comparacion(self):
        c = json.loads(api.comparacion_json(json.dumps({"centro": "AVM", "tau": 2, "pasos": 10, "trayectorias": 50})))
        cur = c["curvas"]
        for k in ("coherente", "medido", "ventanas", "clasico"):
            self.assertEqual(len(cur[k]["origen"]), 11)
            self.assertAlmostEqual(cur[k]["origen"][0], 1.0, places=6)
        # Efecto Zeno: medido cada τ = 2 se queda más en el origen que el walk coherente
        self.assertGreater(cur["medido"]["origen"][5], cur["coherente"]["origen"][5])


@unittest.skipUnless(REAL, "las figuras usan Qiskit real (draw('mpl'), plot_histogram)")
class TestFiguras(unittest.TestCase):
    SVG = "data:image/svg+xml;base64,"

    def test_microcircuito(self):
        f = json.loads(api.figuras_json(json.dumps({"tipo": "micro", "preset": "toque-6", "t": 30, "pasos": 2})))
        self.assertTrue(f["circuito_svg"].startswith(self.SVG))
        self.assertTrue(f["histograma_svg"].startswith(self.SVG))
        self.assertEqual(f["histograma_tipo"], "ideal")
        self.assertEqual(f["ops"]["rx"], 1)

    def test_paso_con_conteos(self):
        p = {"centro": "AVM", "tau": 5, "shots": 100, "pasos_trotter": 1, "semilla": 2}
        r = json.loads(api.paso_json(backend_de_prueba(), json.dumps(p)))
        self.assertEqual(sum(r["conteos"].values()), 100)
        for vista, nombre in (("compacta", "PauliEvolution"), ("expandida", "rxx")):
            f = json.loads(api.figuras_json(json.dumps({"tipo": "paso", **p, "vista": vista, "conteos": r["conteos"]})))
            self.assertIn(nombre, f["ops"])
            self.assertEqual(f["histograma_tipo"], "medido")
            self.assertEqual(f["neuronas"], r["ventana"])

    def test_etiquetas_de_estado(self):
        from cerebro_q import visual
        self.assertEqual(visual.etiqueta_estado("000", ["A", "B", "C"]), "∅ (nadie)")
        self.assertEqual(visual.etiqueta_estado("101", ["A", "B", "C"]), "A+C")  # qubit 0 = derecha


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
