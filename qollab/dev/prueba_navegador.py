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
        assert pag.is_visible("#chap-1") and not pag.is_visible("#chap-2"), "sólo debe verse el capítulo 1"
        print("narración 1:", pag.inner_text("#narr-text")[:140])
        pag.screenshot(path=str(out / "1_inicio.png"))
        # ayuda "?" y ajustes de laboratorio
        pag.click('button.help[data-help="theta"]')
        assert pag.is_visible("#help-pop"), "la ayuda no se abrió"
        pag.keyboard.press("Escape")
        assert not pag.is_visible("#help-pop"), "Esc debe cerrar la ayuda"
        pag.click("#lab-btn")
        assert pag.is_visible("#gamma"), "el cajón de laboratorio no se abrió"
        pag.screenshot(path=str(out / "1b_lab.png"))
        pag.keyboard.press("Escape")
        assert not pag.is_visible("#lab"), "Esc debe cerrar el laboratorio"
        # capítulo 3 · circuito; las pestañas se mueven con flechas
        pag.focus("#tab-1")
        pag.keyboard.press("ArrowLeft")
        assert pag.is_visible("#chap-3"), "← desde la pestaña 1 debe ir a la 3"
        pag.click("#run-btn")
        pag.wait_for_selector("#run-result table", timeout=60000)
        print("backend local:", pag.inner_text("#run-result").splitlines()[0])
        pag.click("#run-btn")  # local: se puede volver a ejecutar
        pag.wait_for_selector("#run-result table", timeout=60000)
        pag.screenshot(path=str(out / "2_backend_local.png"))
        print("estado SR:", pag.inner_text("#sr-status"))

        # 1b) cascada cuántica: 6 pasos, cada uno un circuito en el backend
        pag.click("#lab-btn")
        pag.fill("#casc-pasos", "6")
        pag.click("#lab-close")
        pag.click("#tab-2")
        pag.focus("#scene")
        for _ in range(4):
            pag.keyboard.press("+")
        pag.click("#casc-btn")
        pag.wait_for_function("document.querySelectorAll('#casc-log li').length > 0", timeout=120000)
        pag.wait_for_function("document.querySelector('#narr-kicker').textContent.includes('superposition')", timeout=60000)
        pag.wait_for_timeout(300)
        pag.screenshot(path=str(out / "4a_superposicion.png"))
        pag.wait_for_timeout(900)
        pag.screenshot(path=str(out / "4a2_colapsando.png"))
        pag.wait_for_function("document.querySelector('#narr-kicker').textContent.includes('measured')", timeout=60000)
        pag.wait_for_timeout(150)
        pag.screenshot(path=str(out / "4b_colapso.png"))
        pag.wait_for_function("document.querySelector('#casc-stop').disabled && "
                              "document.querySelectorAll('#casc-log li').length > 0", timeout=120000)
        assert pag.is_visible("#mini-circ svg"), "falta el circuito del paso"
        print("cascada:", pag.inner_text("#casc-estado"))
        print("narración 2:", pag.inner_text("#narr-text")[:160])
        pag.click("#cmp-box summary")
        pag.click("#cmp-btn")
        pag.wait_for_selector("#cmp-dist svg", timeout=60000)
        pag.locator("#casc-bars").scroll_into_view_if_needed()
        pag.wait_for_timeout(800)
        pag.screenshot(path=str(out / "4_cascada.png"))
        pag.locator("#cmp-dist").scroll_into_view_if_needed()
        pag.screenshot(path=str(out / "5_comparacion.png"))

        # 2) Givens + otro preset
        pag.click("#tab-3")
        pag.select_option("#preset", "toque-bilateral-10")
        pag.check('input[value="givens"]', force=True)
        pag.wait_for_function("document.querySelector('#compile-btn').disabled === false && "
                              "document.querySelector('#chips').textContent.includes('Givens')", timeout=60000)
        print("givens:", pag.inner_text("#chips").replace("\n", " "))
        pag.wait_for_timeout(500)
        pag.screenshot(path=str(out / "6_circuito.png"))

        # 3) IonQ imitado: un job por ejecución
        pag.goto(a.url + "/?backend=ionq")
        pag.wait_for_function("document.querySelector('#chips').children.length > 0", timeout=60000)
        pag.click("#tab-3")
        print("pill:", pag.inner_text("#backend-pill"))
        pag.click("#run-btn")
        pag.wait_for_selector("#run-result table", timeout=60000)
        assert pag.is_disabled("#run-btn"), "IonQ debería quedar en un job por ejecución"
        print("ionq: botón deshabilitado tras 1 job ✓")
        assert pag.is_disabled("#casc-btn"), "la cascada también debe quedar bloqueada en IonQ"
        print("ionq: cascada bloqueada tras el job ✓")

        # 4) hardware imitado: pide confirmación
        pag.goto(a.url + "/?backend=qpu")
        pag.wait_for_function("document.querySelector('#chips').children.length > 0", timeout=60000)
        pag.click("#tab-3")
        pag.click("#run-btn")
        assert "Confirm" in pag.inner_text("#run-btn"), "falta la confirmación de hardware"
        print("qpu: pide confirmación ✓")

        # 5) teclado y pantalla angosta
        pag.click("#tab-1")
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
