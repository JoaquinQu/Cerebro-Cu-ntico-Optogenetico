"""Prueba de humo en un navegador sin ventana (Playwright + Chromium).

    python dev/servidor.py &          # en otra terminal
    python dev/prueba_navegador.py [--url http://127.0.0.1:8765] [--salida capturas/]

Comprueba que la página arranca, que el láser produce el quantum walk, que el microcircuito
se simula, que el job corre en el backend y que IonQ queda limitado a un job por ejecución.
"""

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--salida", default="capturas")
    a = ap.parse_args()
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    errores = []
    with sync_playwright() as p:
        nav = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pag = nav.new_page(viewport={"width": 1440, "height": 860})
        pag.on("pageerror", lambda e: errores.append(f"pageerror: {e}"))
        pag.on("console", lambda m: m.type == "error" and errores.append(f"console: {m.text}"))

        # 1) backend local
        pag.goto(a.url)
        pag.wait_for_selector("#loader.hide", timeout=60000)
        pag.wait_for_function("document.querySelector('#chips').children.length > 0", timeout=60000)
        pag.wait_for_timeout(2500)
        assert pag.inner_text("#m-top") not in ("", "—"), "el quantum walk no se dibujó"
        pag.screenshot(path=str(out / "1_inicio.png"))
        pag.click("#run-btn")
        pag.wait_for_selector("#run-result table", timeout=60000)
        print("backend local:", pag.inner_text("#run-result").splitlines()[0])
        pag.click("#run-btn")  # local: se puede volver a ejecutar
        pag.wait_for_selector("#run-result table", timeout=60000)
        pag.locator("#panel-q").scroll_into_view_if_needed()
        pag.screenshot(path=str(out / "2_backend_local.png"))
        print("estado SR:", pag.inner_text("#sr-status"))

        # 2) Givens + otro preset
        pag.select_option("#preset", "toque-bilateral-10")
        pag.check('input[value="givens"]', force=True)
        pag.wait_for_function("document.querySelector('#compile-btn').disabled === false && "
                              "document.querySelector('#chips').textContent.includes('Givens')", timeout=60000)
        print("givens:", pag.inner_text("#chips").replace("\n", " "))

        # 3) IonQ imitado: un job por ejecución
        pag.goto(a.url + "/?backend=ionq")
        pag.wait_for_function("document.querySelector('#chips').children.length > 0", timeout=60000)
        print("pill:", pag.inner_text("#backend-pill"))
        pag.click("#run-btn")
        pag.wait_for_selector("#run-result table", timeout=60000)
        assert pag.is_disabled("#run-btn"), "IonQ debería quedar en un job por ejecución"
        print("ionq: botón deshabilitado tras 1 job ✓")

        # 4) hardware imitado: pide confirmación
        pag.goto(a.url + "/?backend=qpu")
        pag.wait_for_function("document.querySelector('#chips').children.length > 0", timeout=60000)
        pag.click("#run-btn")
        assert "Confirmar" in pag.inner_text("#run-btn"), "falta la confirmación de hardware"
        print("qpu: pide confirmación ✓")

        # 5) teclado y pantalla angosta
        pag.focus("#scene")
        pag.keyboard.press("ArrowRight")
        print("teclado:", pag.inner_text("#time-label"))
        pag.set_viewport_size({"width": 700, "height": 900})
        pag.wait_for_timeout(800)
        pag.screenshot(path=str(out / "3_movil.png"), full_page=True)
        nav.close()
    if errores:
        print("\n".join(errores))
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
