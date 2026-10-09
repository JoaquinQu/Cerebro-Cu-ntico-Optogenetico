# Plan: quantum walk por ventanas ("cascada de spikes")

**Idea (propuesta del equipo).** Después de que el láser excita una neurona, se arma un circuito cuántico con esa neurona y sus 9 vecinas (10 qubits). Se deja evolucionar el walk un tiempo τ y se mide. La neurona que "disparó" pasa a ser el nuevo centro, y se repite. Cada salto que se ve en el gusano 3D sale de medir un circuito de Qiskit, no de numpy.

**Por qué vale la pena.** Resuelve el punto débil del proyecto: hoy lo más visible, el gusano completo, sale de un cálculo clásico. Con esto la parte cuántica pasa a mover la animación.

Estado: **implementado** en `qollab/cerebro_q/cascada.py` y en el panel 2 de la página (ver §5). Quedan abiertas las tareas 8–9 (texto y video). Todas las cifras de este plan se calcularon con pesos binarios (la decisión del equipo) y el código actual (`qollab/cerebro_q`).

---

## 1. Cómo funciona un paso

1. **Centro** c: la neurona excitada (al inicio, la del láser).
2. **Ventana**: c + 9 vecinas → 10 qubits. Los acoplamientos dentro de la ventana son los mismos de J, restringidos a esas 10 neuronas.
3. **Circuito**: `RX(θ)` en c, luego la evolución XY durante τ con `PauliEvolutionGate` + `SuzukiTrotter` (Qiskit nativo), y medición de los 10 qubits.
4. **Ejecutar** con `backend.run` y S shots (por ejemplo 200).
5. **Elegir el siguiente centro**: se toma un shot al azar entre los válidos (exactamente un 1). La neurona en 1 es el spike y pasa a ser el nuevo centro. Los S shots se muestran como distribución en la ventana.
6. Repetir K pasos (por ejemplo 15–30).

En el gusano 3D se ven los 10 qubits de la ventana encendidos según los shots, y el spike que salta al siguiente centro. Queda un rastro de los centros anteriores.

## 2. Decisiones de diseño (con datos)

### 2.1 Qué vecinas entran en la ventana

Con pesos binarios todas las conexiones valen lo mismo, así que "las 9 más fuertes" no está definido. Propuesta:

- **Vecinas directas de c, ordenadas por número de sinapsis** (el dato sigue en `connectome_cook2019.csv` aunque J sea binaria). Para AVM la ventana queda: AVM, ALMR, AVDL, PVCR, PVR, ALML, AVBL, PVCL, AVBR, BDUR.
- Si c tiene menos de 9 vecinas (le pasa al 6 % de las neuronas), se completa con neuronas a 2 sinapsis.

Dato importante: el grado mediano del conectoma es ~20 y el máximo 99. La ventana de 10 casi nunca contiene a todas las vecinas.

### 2.2 El tiempo por paso τ: la decisión más importante

Una ventana de 10 neuronas está **aislada** del resto: en la red real, la excitación también se escaparía hacia las otras vecinas. El escape crece con τ. Esta es la mediana sobre todas las neuronas, con el walk exacto de la red completa:

| τ (unidades de 1/γ) | Probabilidad de que la excitación siga dentro de la ventana | Probabilidad de que siga en el centro |
| --- | --- | --- |
| 2 | 0.96 | 0.93 |
| 3 | 0.91 | 0.86 |
| 5 | 0.77 | 0.67 |
| 10 (AVM) | 0.29 | 0.19 |

Aquí aparece una tensión real:

- **τ chico (2–3)** → la ventana representa bien a la red, pero en ~90 % de los pasos la medición devuelve el mismo centro. Medir tan seguido "congela" el walk: es el **efecto Zeno cuántico**. Se necesitan muchos pasos para ver movimiento.
- **τ grande (≥ 8)** → la excitación sí se mueve, pero cada paso ya no es la red real: es el walk sobre un microcircuito aislado de 10 neuronas. Es un modelo válido si se dice así, pero no se puede presentar como el walk del gusano completo.

Simulando la cascada completa desde AVM (200 cascadas de 20 pasos, walk exacto en cada ventana):

| τ | Pasos en que el spike se queda en el centro | Neuronas distintas visitadas en 20 pasos (mediana) |
| --- | --- | --- |
| 3 | 92 % | 2 |
| 5 | 81 % | 4 |
| 8 | 60 % | 8 |

**Recomendación:** τ como deslizador, con 8 por defecto para que la cascada se mueva, presentando cada paso como "el walk en el microcircuito local". La página muestra al lado cuánto se escapa de la ventana para ese τ. Al bajar τ se ve en vivo el congelamiento por medición (Zeno). La animación salta rápido los pasos en que el centro no cambia.

### 2.3 Qué se pierde al medir (y por qué es lo mejor de la idea)

Al medir, el estado colapsa: la interferencia existe **dentro** de cada paso, pero no se arrastra de un paso al siguiente. La cadena de spikes es, en conjunto, una caminata **aleatoria clásica**, cuyos saltos los decide un walk cuántico.

Esto no es un defecto si se presenta bien: es la transición cuántico → clásico por medición, el tema *Quantum Unlocked*. La página compara cuatro curvas para el mismo láser y el mismo τ (distancia media al origen y probabilidad de seguir en el origen):

1. **coherente**: el walk sin medir (exacto, red completa);
2. **medido cada τ**: el walk medido cada τ en la red completa. Es exactamente una cadena de Markov clásica con probabilidades de salto T_ij = |[e^(−iγJτ)]_ij|², el límite de ventana infinita;
3. **cascada**: lo que hacen los circuitos de 10 qubits (simulado con numpy para la comparación);
4. **clásica**: una caminata aleatoria común, dp/dt = −γLp.

Lo que muestran los números (AVM, distancia media al origen en t = 24):

| τ | coherente | medido cada τ | cascada (10 qubits) | clásica |
| --- | --- | --- | --- | --- |
| 2 | 1.87 | 0.90 | 0.36 | 2.12 |
| 4 | 1.87 | 1.38 | 0.64 | 2.12 |
| 8 | 1.87 | 1.74 | 0.98 | 2.12 |

- Medir convierte el walk en un proceso clásico (sin interferencia entre pasos), pero **no** en la caminata clásica común: con τ chico la medición frena la propagación (**efecto Zeno**). La probabilidad de saltar en un paso es ≈ (γJτ)², así que el ritmo efectivo cae como τ.
- La cascada de 10 qubits se propaga más lento que el walk medido en la red completa, porque la ventana no deja que la excitación se escape a las otras vecinas. Esa diferencia es el costo de cortar la red en ventanas, y conviene decirlo.

### 2.4 Costo del circuito

Dentro de una ventana hay entre 25 (mediana) y 38 (máximo) aristas, porque las vecinas también están conectadas entre sí. Un paso de Strang (r = 1) son ~98 compuertas de dos qubits (p90: 122):

- **Simulador del navegador** (hasta 24 qubits): 10 qubits y ~100 compuertas es trivial.
- **Hardware IonQ**: una fidelidad estimada de 0.996^98 ≈ 0.67 es viable, pero solo para el **primer paso**: IonQ acepta **un job por ejecución** y aquí cada paso depende del anterior. En los simuladores locales no hay límite, y ahí corren los jurados.

### 2.5 Shots sin spike o con dos spikes

Con ruido aparecen shots con 0 o con 2+ excitaciones. Se aplica la misma post-selección de siempre: solo cuentan los shots con exactamente un 1 (con θ = π el estado ideal no tiene vacío). Si un paso no deja ningún shot válido, la cadena termina y se muestra "la señal se perdió".

---

## 3. Tareas

| # | Tarea | Dueño | Dónde | Hecho cuando |
| --- | --- | --- | --- | --- |
| 1 | `ventana(c, k=10)`: vecinas por número de sinapsis, completar a distancia 2 | P1 | `cerebro_q/fisica.py` | Test: 10 neuronas, c primero, todas conectadas al resto de la ventana |
| 2 | Hamiltoniano de la ventana como `SparsePauliOp` + `PauliEvolutionGate(SuzukiTrotter)` | P2 | `cerebro_q/circuitos.py` | Test: igual (TVD < 1e-3 con r alto) al walk exacto de la ventana |
| 3 | `paso_json(backend, centro, tau, shots, semilla)`: un circuito, un job, distribución + spike elegido | P2 | `cerebro_q/api.py` | Devuelve ventana, conteos, distribución post-seleccionada y nuevo centro |
| 4 | Bucle de cascada en JS: K pasos, pausa/continuar, tope de pasos, aviso si el backend es IonQ (1 paso) | P3 | `main.js` | Corre 20 pasos en el simulador del navegador sin congelar la página |
| 5 | Animación: ventana iluminada por shots, spike que salta, rastro de centros | P3 | `js/escena.js` | Se entiende qué neurona disparó en cada paso sin leer texto |
| 6 | Comparación coherente vs. por ventanas vs. clásica (M trayectorias simuladas con numpy, rápido) | P1 | `cerebro_q/analisis.py` + gráfico | Gráfico con las 3 curvas; la de ventanas se acerca a la clásica al bajar τ |
| 7 | Accesibilidad: anuncio en `aria-live` de cada spike ("paso 4: dispara AVDL"), tabla de la cadena | P3 | `main.js` | Se puede seguir la cascada con lector de pantalla |
| 8 | Texto: explicar Zeno y la transición cuántico → clásico (sección corta en el doc de quantum walks y en la página de Qollab) | P4 | docs + Project Card | Un párrafo y una figura |
| 9 | Guion del video: mostrar la cascada como momento central | P4 | — | 20–30 s del video |

**Orden sugerido:** 1 → 2 → 3 (núcleo Python, probado con el arnés `dev/`), en paralelo 4–5 con datos falsos, luego 6–7, y 8–9 al final.

## 4. Preguntas abiertas para el equipo

- ¿El siguiente centro sale de un shot al azar (más fiel y vistoso, cada corrida distinta) o de la neurona más probable (determinista)? La propuesta es un shot al azar, con una semilla opcional para el video.
- ¿τ por defecto 8 (más movimiento, cada paso es un microcircuito aislado) o 5 (más fiel a la red, más lento)?
- ¿Cuántos pasos por cascada? Con 20 pasos se recorren ~8 neuronas distintas con τ = 8 y ~4 con τ = 5.

---

## 5. Implementación (lo que quedó hecho)

- **Python** (`qollab/cerebro_q/cascada.py`):
  - `ventana(c)`: elige las vecinas por número de sinapsis y completa a distancia 2.
  - `circuito_paso`: arma el circuito con `PauliEvolutionGate` + `SuzukiTrotter` (o con RXX/RYY equivalentes si esa API no existe).
  - `ejecutar_paso`: un job por paso, post-selección, spike elegido de un shot al azar; si el shot es vacío, la neurona no disparó.
  - `comparacion`: calcula las 4 curvas.
  - Funciones de la API: `paso_json` y `comparacion_json`.
- **Página** (`main.js`, panel 2 "Cascada cuántica de spikes"):
  - controles: deslizador de τ (2–12, por defecto 8), número de pasos y de shots, Iniciar/Detener;
  - en el gusano: la ventana iluminada por lo medido, anillos en sus 10 neuronas, un destello en el spike y un rastro de los centros;
  - por paso: chips con qubits, compuertas 2q, shots válidos, fuga de la ventana y spike;
  - barras de teoría vs. medido, con su tabla;
  - la lista "Cadena de spikes" y la comparación con 4 curvas y su tabla;
  - anuncios en `aria-live`.
- **Pasos de Trotter por ventana**: 1 si τ ≤ 4.5, 2 si τ ≤ 9 y 3 por encima (TVD ≤ 0.025 contra la evolución exacta de la ventana).
- **IonQ**: un solo paso (un job). El botón se bloquea después, también si ya se usó el job del microcircuito. Si el backend es hardware, pide confirmación.
- **Pruebas**: 5 nuevas en `tests/test_cerebro_q.py`:
  - la ventana;
  - el circuito contra la teoría (con Qiskit real compara además `PauliEvolutionGate` vía `Statevector`);
  - un paso en el backend;
  - un paso sin disparo;
  - el efecto Zeno en la comparación.

  La prueba de navegador corre una cascada de 6 pasos y la comparación.

**Pendiente de verificar con Qiskit real** (este entorno no lo tiene). Hay dos formas:

- correr las pruebas en tu `.venv`: `python -m unittest discover -s tests` dentro de `qollab/`;
- o una primera corrida en Qollab con el *Built-in simulator*.
