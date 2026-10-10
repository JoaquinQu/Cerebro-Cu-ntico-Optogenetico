"""Arnés de desarrollo: prueba la página de Qollab en tu computador, sin Qollab.

    python dev/servidor.py            → http://127.0.0.1:8765
    python dev/servidor.py --puerto 9000

Qué imita:
  * Qollab pega index.html dentro del <body>, carga main.css y main.js, y deja importar
    `three` y los módulos Python por nombre. Aquí se arma esa página con un importmap:
    `three` → three.js vendorizado del prototipo y `cerebro_q.api` → dev/puente_api.js,
    que llama a cerebro_q/api.py por HTTP (mismas funciones, mismos JSON).
  * `backend`: con Qiskit instalado se usa BasicSimulator; si no, el backend numpy de
    dev/qiskit_simulado. Con ?backend=ionq o ?backend=qpu se imita un backend de IonQ
    (simulador remoto u hardware) para probar la regla de "un job por ejecución".

Nada de esta carpeta se sube a Qollab (ver docs/QOLLAB.md).
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RAIZ = Path(__file__).resolve().parent.parent  # qollab/
VENDOR = RAIZ.parent / "frontend" / "vendor" / "three"
os.chdir(RAIZ)  # las rutas literales de cerebro_q/datos.py son relativas a la raíz del proyecto
sys.path.insert(0, str(RAIZ))
try:
    import qiskit  # noqa: F401

    QISKIT_REAL = not getattr(qiskit, "SIMULADO", False)
except ImportError:
    sys.path.insert(0, str(RAIZ / "dev" / "qiskit_simulado"))
    QISKIT_REAL = False

from cerebro_q import api  # noqa: E402

FUNCIONES = {"conectoma_json", "walk_json", "cuerpo_glb", "microcircuitos_json", "simular_json",
             "backend_json", "ejecutar_json", "paso_json", "comparacion_json", "figuras_json"}


def crear_backend(tipo: str):
    if QISKIT_REAL:
        from qiskit.providers.basic_provider import BasicSimulator

        base = BasicSimulator()
    else:
        from qiskit import BackendSimulado

        base = BackendSimulado()
    if tipo in ("ionq", "qpu"):
        nombre = "ionq_simulator" if tipo == "ionq" else "ionq_qpu.forte-1"

        class BackendIonQImitado:  # sólo cambia el nombre: la simulación es local
            __module__ = "qiskit_ionq.imitado"
            name = nombre
            num_qubits = 36

            def run(self, *a, **k):
                return base.run(*a, **k)

            def __getattr__(self, k):
                return getattr(base, k)

        return BackendIonQImitado()
    return base


def pagina() -> str:
    cuerpo = (RAIZ / "index.html").read_text(encoding="utf-8")
    cuerpo = re.sub(r"<script\b.*?</script>", "", cuerpo, flags=re.S | re.I)  # Qollab no ejecuta <script>
    imports = {
        "three": "/vendor/three/three.module.js",
        "three/addons/": "/vendor/three/addons/",
        "cerebro_q.api": "/dev/puente_api.js",
    }
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cerebro Cuántico Optogenético · arnés local</title>
<link rel="stylesheet" href="/main.css">
<style>body{{margin:0;background:#020308;padding:12px}}</style>
<script type="importmap">{json.dumps({"imports": imports})}</script>
<script>globalThis.backend = {{ __dev__: true }};</script>
</head><body>
{cuerpo}
<script type="module" src="/main.js"></script>
</body></html>"""


class Manejador(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # silencioso salvo errores
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def _enviar(self, codigo: int, cuerpo: bytes, tipo: str):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        ruta = urlparse(self.path).path
        if ruta in ("/", "/index.html"):
            return self._enviar(200, pagina().encode(), "text/html; charset=utf-8")
        if ruta.startswith("/vendor/three/"):
            archivo = (VENDOR / ruta[len("/vendor/three/"):]).resolve()
            base = VENDOR.resolve()
        else:
            archivo = (RAIZ / ruta.lstrip("/")).resolve()
            base = RAIZ.resolve()
            # Igual que en Qollab, JS no puede leer los datos del proyecto
            if archivo.is_relative_to(RAIZ / "data"):
                return self._enviar(403, b"JS no puede leer archivos del proyecto en Qollab", "text/plain")
        if not archivo.is_relative_to(base) or not archivo.is_file():
            return self._enviar(404, b"no encontrado", "text/plain")
        tipo = mimetypes.guess_type(archivo.name)[0] or "application/octet-stream"
        if archivo.suffix in (".js", ".mjs"):
            tipo = "text/javascript"
        self._enviar(200, archivo.read_bytes(), tipo)

    def do_POST(self):
        url = urlparse(self.path)
        nombre = url.path.removeprefix("/api/")
        if nombre not in FUNCIONES:
            return self._enviar(404, b"funcion desconocida", "text/plain")
        tipo = parse_qs(url.query).get("backend", ["local"])[0]
        try:
            args = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"[]")
            args = [crear_backend(tipo) if a == "__backend__" else a for a in args]
            if nombre in ("backend_json", "ejecutar_json", "paso_json") and tipo == "none":
                raise RuntimeError("sin backend")
            salida = getattr(api, nombre)(*args)
            self._enviar(200, salida.encode("utf-8"), "application/json; charset=utf-8")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._enviar(500, f"{type(e).__name__}: {e}".encode(), "text/plain; charset=utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puerto", type=int, default=8765)
    a = ap.parse_args()
    print(f"Qiskit {'real' if QISKIT_REAL else 'simulado (dev/qiskit_simulado)'} · http://127.0.0.1:{a.puerto}")
    print("  ?backend=ionq  imita el simulador remoto de IonQ   ?backend=qpu  imita hardware IonQ")
    ThreadingHTTPServer(("127.0.0.1", a.puerto), Manejador).serve_forever()


if __name__ == "__main__":
    main()
