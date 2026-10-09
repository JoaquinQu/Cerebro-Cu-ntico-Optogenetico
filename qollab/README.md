# Cerebro Cuántico Optogenético · proyecto Qollab (JS / Qiskit)

Esta carpeta es la versión del proyecto que corre **dentro de Qollab.xyz**: la página (HTML, CSS, three.js) llama a un núcleo Python con Qiskit que se ejecuta en el navegador mediante Pyodide. El circuito va al `backend` que elige quien presiona **Run**.

This effort is supported by Qollab & IonQ.

## Qué se sube a Qollab

Se suben solo estos archivos. Son 20 en total (18 sin README ni LICENSE) y pesan cerca de 1 MB, con lo que se respeta el límite de 100 archivos de 2 MB cada uno.

```
index.html              cuerpo de la página (sin <script>, Qollab lo pega en <body>)
main.js                 orquesta la página e importa cerebro_q.api por su nombre de módulo
main.css                estilos (el único CSS que carga Qollab)
requirements.txt        numpy y scipy (Qiskit lo instala Qollab)
js/escena.js            escena 3D (three 0.186, importado por nombre)
js/graficos.js          gráficos SVG y tablas accesibles
js/python.js            puente: .callPromising + JSON
cerebro_q/              núcleo Python: datos, física, circuitos Qiskit, cascada por ventanas, análisis, api
data/neurons.json       posiciones de las 302 neuronas (OpenWorm)
data/connectome_cook2019.csv   sinapsis (Cook et al. 2019)
data/gusano.glb         cuerpo 3D (lo lee Python y lo entrega en base64)
README.md, LICENSE      (opcionales) documentación y licencia MIT
```

Estas carpetas **no se suben**, porque son solo para desarrollo: `dev/` y `tests/`.

### Pasos en Qollab

1. **+ New Project** → tipo **HTML/JS**. Borra los archivos de ejemplo.
2. Sube los archivos de la lista **respetando las carpetas** (`js/`, `cerebro_q/`, `data/`).
3. Presiona **Run** y elige **Built-in simulator**. Deberías ver el gusano, la propagación y el panel del microcircuito.
4. En **Ejecutar circuito** se envía un job (4 tiempos en un solo `backend.run`).
5. Para el simulador de IonQ, presiona **Stop**, luego **Run** y elige **IonQ Forte 1 (Remote simulator)**. Es gratis, pero IonQ admite **un job por ejecución**.
6. Para el hardware **IonQ Forte 1 (Quantum computer)**, que usa créditos, la página pide confirmar con un segundo clic.
7. Copia el texto de la sección *Project Card* (abajo) en la página del proyecto y **publica**.

> **Pendiente de verificar en Qollab:** el entorno donde se construyó no tiene Qiskit real. Las pruebas usaron una imitación mínima (`dev/qiskit_simulado`) y la física se comparó con numpy. La primera corrida en Qollab sobre el *Built-in simulator* confirma `transpile`, el dibujo de texto del circuito y `get_counts(i)` con Qiskit 2.x.

## Cómo funciona

| Paso | Dónde corre | Qué hace |
| --- | --- | --- |
| 1 · Láser | Python (numpy) | Calcula el quantum walk exacto sobre las 302 neuronas: P<sub>k</sub>(t) = sin²(θ/2)·\|⟨k\|e<sup>−iγJt</sup>\|j⟩\|². No usa el backend. |
| 2 · Cascada cuántica | Python + Qiskit + `backend.run` | Cada paso es un circuito de 10 qubits: la neurona que disparó y sus 9 vecinas con más sinapsis. Evolución XY con `PauliEvolutionGate` + `SuzukiTrotter` durante τ, **un job por paso**, medición. La neurona en 1 de un shot al azar dispara el paso siguiente. Incluye la comparación coherente / medido / cascada / clásica (efecto Zeno). |
| 3 · Microcircuito | Python + Qiskit | Arma un `QuantumCircuit` con RX(θ) (el láser) y RXX(α)·RYY(α) (el salto XY) por Trotter–Suzuki o con una cascada de Givens. Compara la teoría exacta, el circuito ideal y el circuito con ruido tipo Forte. |
| 3 · Backend del microcircuito | `backend.run` | Hace **un** job con 1 o 4 circuitos (uno por tiempo t), transpilado con `optimization_level=1`. Mide los conteos, aplica post-selección por simetría (≤ 1 excitación) y calcula la TVD frente a la teoría. |

La teoría completa está en [`../docs/TEORIA.md`](../docs/TEORIA.md).

## Accesibilidad

- **Estructura y etiquetas:** landmarks y encabezados en orden, todos los controles con `<label>`, el modo del circuito como radio-group y `aria-valuetext` en los deslizadores.
- **Alternativa al lienzo 3D:** el lienzo tiene una descripción que se actualiza ("las neuronas más probables son…") y una región `aria-live` con los resultados.
- **Teclado:** con el foco en el lienzo, <kbd>Espacio</kbd> reproduce o pausa, <kbd>←</kbd>/<kbd>→</kbd> mueven el tiempo (con <kbd>Shift</kbd>, más rápido), <kbd>↑</kbd>/<kbd>↓</kbd> giran la vista, <kbd>+</kbd>/<kbd>−</kbd> acercan o alejan y <kbd>R</kbd> centra. Hay un enlace "Saltar a los controles" y el foco es visible.
- **Datos en texto:** cada gráfico tiene su tabla ("Ver datos como tabla") y el circuito se muestra como dibujo de texto de Qiskit.
- **Contraste:** el texto secundario tiene un contraste de 5:1 o más.
- **Menos movimiento:** `prefers-reduced-motion` desactiva la animación automática y el parpadeo del láser.

## Desarrollo local (sin Qollab)

```bash
cd qollab
python -m unittest discover -s tests      # 20 pruebas (física, circuitos, cascada, reglas de Qollab)
python dev/servidor.py                    # http://127.0.0.1:8765  (?backend=ionq | ?backend=qpu)
python dev/prueba_navegador.py            # prueba de humo con Playwright (servidor encendido)
```

`dev/servidor.py` reproduce el entorno de Qollab:

- pega `index.html` dentro de `<body>`;
- usa un importmap para `three` y `cerebro_q.api`;
- crea un `backend` (BasicSimulator si tienes Qiskit, y si no la imitación);
- bloquea que JS lea `data/`, igual que Qollab.

---

## Project Card (texto para la página de Qollab)

**Cerebro Cuántico Optogenético: un láser cuántico sobre el conectoma real de *C. elegans***

**Qué hace.** Ilumina con un "láser" cualquiera de las 302 neuronas del gusano *C. elegans* y muestra en 3D cómo la excitación se propaga como un *quantum walk* sobre su conectoma real (Cook et al., 2019). Después toma un microcircuito del reflejo de toque (6 a 10 neuronas, una por qubit) y lo ejecuta en Qiskit. Se puede correr en el simulador del navegador, en los simuladores con ruido de IonQ o en el hardware IonQ Forte, y comparar el resultado con la teoría exacta.

**Qué problema aborda.** La simulación hamiltoniana es una de las aplicaciones más naturales de un computador cuántico, pero es difícil de *ver*. Este proyecto la vuelve tangible. El pulso del láser es una rotación RX(θ), cada sinapsis es un acoplamiento XY y la propagación es interferencia cuántica. También muestra los pasos reales para llevarla a hardware: la trotterización y su error, la compilación (RXX/RYY → ZZ nativa en IonQ) y la mitigación por simetría (post-selección).

**Cómo correrlo.**

1. Presiona **Run** y elige un backend. Con *Built-in simulator* todo es instantáneo y gratis.
2. Elige una neurona en el panel 1 o haz clic sobre el gusano y presiona **Disparar láser**.
3. En el panel 2, elige el microcircuito, el modo (Trotter o Givens) y el tiempo t.
4. En el panel 2, presiona **Iniciar cascada**. Cada paso es un circuito de 10 qubits ejecutado en el backend; el spike medido salta por el gusano y deja un rastro. Abre "¿Qué cambia al medir?" para ver cómo la medición frena el walk (efecto Zeno).
5. Presiona **Ejecutar circuito**. Se manda un solo job con 4 tiempos. Los puntos naranjos se comparan con las curvas teóricas y aparecen la TVD y la fracción aceptada.
6. Para IonQ, elige *IonQ Forte 1* (simulador remoto, gratis). IonQ acepta un job por Run: la cascada corre un paso.

**Cómo replicarlo.** Todo el código y los datos están en este proyecto y en el repositorio público (MIT): https://github.com/JoaquinQu/Cerebro-Cu-ntico-Optogenetico. Las pruebas automáticas comprueban que la dinámica XY en un sector de una excitación coincide con el walk, que Trotter converge, que Givens es exacto y que la post-selección es correcta. La teoría completa está en `docs/TEORIA.md`.

**Cómo extenderlo.** Hay varias direcciones:

- otros microcircuitos (`cerebro_q/microcircuitos.py`);
- varios láseres a la vez (sectores de 2 excitaciones);
- orden de Trotter superior;
- otros conectomas (por ejemplo, *Drosophila*);
- estimar tiempos de llegada de la señal con hardware real.

**Temas:** Quantum Unlocked · Quantum Playground.

**Créditos y datos.** Conectoma: Cook et al., *Nature* 571 (2019), vía OpenWorm c302. Posiciones: OpenWorm CElegansNeuroML. Reflejo de toque: Chalfie et al. (1985). Optogenética en el gusano: Nagel et al. (2005).

This effort is supported by Qollab & IonQ.
