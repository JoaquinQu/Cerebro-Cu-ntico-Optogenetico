# Teoría del backend: del conectoma a un circuito en IonQ

Este documento explica la física y las decisiones técnicas detrás de `backend/cerebro/`. Cada sección indica el módulo que la implementa y el test que la verifica.

**Resumen en una frase.** Cada neurona de *C. elegans* es un qubit; un pulso de luz (láser optogenético) la rota con una compuerta $R_X(\theta)$; las sinapsis reales del gusano definen un hamiltoniano de saltos tipo XY cuya dinámica, en el sector de una excitación, es exactamente un *quantum walk* sobre el conectoma; medir un qubit en $|1\rangle$ equivale a un "spike" de esa neurona. La red completa (302 neuronas) se resuelve de forma exacta en el computador clásico, y un microcircuito del reflejo de toque (6–14 neuronas) se compila a compuertas nativas de **IonQ Forte** para correr en hardware real.

---

## Índice

1. [Qué es y qué no es este modelo](#1-qué-es-y-qué-no-es-este-modelo)
2. [Datos: del conectoma a una matriz hermítica](#2-datos-del-conectoma-a-una-matriz-hermítica)
3. [Hamiltoniano XY y quantum walk](#3-hamiltoniano-xy-y-quantum-walk)
4. [El láser optogenético como rotación de Rabi](#4-el-láser-optogenético-como-rotación-de-rabi)
5. [Medición: el spike y la ley de conservación](#5-medición-el-spike-y-la-ley-de-conservación)
6. [Del hamiltoniano al circuito en IonQ](#6-del-hamiltoniano-al-circuito-en-ionq)
7. [Presupuesto de errores y elección de parámetros](#7-presupuesto-de-errores-y-elección-de-parámetros)
8. [Mitigación de errores y protocolo experimental](#8-mitigación-de-errores-y-protocolo-experimental)
9. [Verificación numérica implementada](#9-verificación-numérica-implementada)
10. [Extensiones posibles](#10-extensiones-posibles)
11. [Referencias](#11-referencias)

---

## 1. Qué es y qué no es este modelo

**Es** una dinámica cuántica coherente definida sobre la red de sinapsis real de *C. elegans*, excitada por un pulso local que imita la estimulación optogenética. Usa la estructura del conectoma como "pista" por la que viaja una excitación cuántica, y permite comparar teoría exacta, simulación con ruido y hardware real.

**No es** un modelo biofísico de neuronas. Las neuronas reales son sistemas disipativos y clásicos a esta escala (potenciales de membrana, canales iónicos, ~ms); aquí no se afirma que el cerebro sea cuántico. La analogía es estructural:

| Optogenética real | Este modelo |
|---|---|
| Luz azul (~470 nm) abre la channelrhodopsina-2 | Pulso de control rota el qubit: $R_X(\theta)$ |
| Intensidad × duración del pulso | Ángulo de Rabi $\theta = \Omega\,\tau$ |
| Probabilidad de disparo según la dosis de luz | $P(\text{disparo}) = \sin^2(\theta/2)$ |
| La actividad viaja por las sinapsis | La excitación salta por los acoplamientos $J_{ij}$ |
| Registro de calcio / electrofisiología | Medición en base $Z$: $|1\rangle$ = spike |

**Honestidad sobre la ventaja cuántica.** Con un solo láser, la dinámica vive en el sector de una excitación (dimensión $n$), que es clásicamente simulable en tiempo polinomial: así resolvemos las 302 neuronas. El hardware no "gana" aquí; demuestra la física. Con $k$ láseres simultáneos, el sector tiene dimensión $\binom{n}{k}$ y la exclusión (un qubit no admite dos excitaciones) introduce interacción efectiva (bosones de núcleo duro). Ahí la simulación clásica crece combinatoriamente y la evolución de Trotter en hardware es el camino natural (§10).

---

## 2. Datos: del conectoma a una matriz hermítica

*Módulo:* `cerebro/connectome.py` · *Datos:* `backend/data/`

**Fuentes.**

- Sinapsis químicas y uniones gap del hermafrodita adulto: **Cook et al., *Nature* 2019**, distribuidas por OpenWorm (`c302/data/herm_full_edgelist.csv`). Tras filtrar a las 302 neuronas del sistema nervioso y normalizar nombres (`DA01` → `DA1`), quedan 3 604 conexiones químicas dirigidas y 2 155 entradas eléctricas.
- Posición 3D del soma y clasificación (sensorial / interneurona / motora) de **OpenWorm CElegansNeuroML**: 302 neuronas, eje anteroposterior de −312 a 410 µm.
- Sólo CANL/CANR quedan aisladas, porque no tienen sinapsis en el conjunto de datos.

**Simetrización.** Un hamiltoniano debe ser hermítico. Para el par $(i,j)$ con $c_{i\to j}$ sinapsis químicas y $g_{ij}$ contactos gap se define

$$
n_{ij} = c_{i\to j} + c_{j\to i} + \max(g_{ij}, g_{ji}),\qquad
W_{ij} = \log(1 + n_{ij}).
$$

El logaritmo comprime la cola pesada de conteos sinápticos, para que pocas conexiones muy gruesas no dominen la dinámica. También están disponibles `binary` (1 si existe conexión) y `count` (conteo crudo). **Limitación:** la dirección de la sinapsis química se pierde (§10).

**Normalización espectral.**

$$
J = \frac{W}{\lambda_{\max}(W)},\qquad \|J\|_2 = 1 .
$$

Con esto el tiempo queda en unidades de $1/\gamma$, el tiempo de salto característico del nodo más conectado. Para el peso `log`, $\lambda_{\max}(W) \approx 60.2$, y en el circuito de toque $J_{ij}\in[0.027, 0.064]$. Un microcircuito usa **la misma escala global**: $J_{\text{sub}} = J[S,S]$. Así su hamiltoniano es literalmente la restricción del de la red completa. Al restringir, el microcircuito se trata como **aislado**: se ignoran sus acoplamientos con las otras ~290 neuronas. Por eso su dinámica no coincide con la de esas mismas neuronas dentro de la red completa; es un modelo del circuito de toque por sí solo, igual que en los experimentos que lo estudian aislado.

---

## 3. Hamiltoniano XY y quantum walk

*Módulo:* `cerebro/hamiltonian.py` · *Test:* `tests/test_physics.py`

Asignamos un qubit a cada neurona ($|0\rangle$ en reposo, $|1\rangle$ excitada) y definimos

$$
H \;=\; \gamma \sum_{i<j} J_{ij}\,\frac{X_iX_j + Y_iY_j}{2}
\;=\; \gamma \sum_{i<j} J_{ij}\left(\sigma_i^{+}\sigma_j^{-} + \sigma_i^{-}\sigma_j^{+}\right).
$$

Es el modelo XY, o de bosones de núcleo duro, sobre el grafo del conectoma: cada término mueve una excitación de $j$ a $i$ con amplitud $\gamma J_{ij}$.

**Propiedad 1: conservación.** $[H, \hat N] = 0$ con $\hat N = \sum_k \tfrac{1}{2}(1 - Z_k)$. Cada término $\sigma^+_i\sigma^-_j$ destruye una excitación y crea otra.

**Propiedad 2: el vacío es estacionario.** $H\,|0\cdots0\rangle = 0$.

**Propiedad 3: equivalencia con el quantum walk.** Sea $|e_k\rangle$ el estado con sólo la neurona $k$ excitada. Entonces $\sigma^+_i\sigma^-_j |e_k\rangle = \delta_{jk}|e_i\rangle$, y por lo tanto

$$
H\,|e_k\rangle = \gamma\sum_i J_{ik}\,|e_i\rangle
\quad\Longrightarrow\quad
H\big|_{\text{1 excitación}} = \gamma J .
$$

La evolución en ese sector es el **quantum walk de tiempo continuo** (Farhi & Gutmann 1998) con hamiltoniano $\gamma J$:

$$
\langle e_k | e^{-iHt} | e_j\rangle = \big[e^{-i\gamma J t}\big]_{kj}.
$$

**Cálculo exacto en 302 neuronas.** $J$ es real y simétrica, con $J = V\Lambda V^{\top}$. Se diagonaliza una vez y, para cualquier $t$,

$$
\big[e^{-i\gamma Jt}\big]_{kj} = \sum_m V_{km}\,e^{-i\gamma\lambda_m t}\,V_{jm},
$$

lo que cuesta $O(N^2)$ por fotograma. La animación de 120 fotogramas de la red completa se calcula en milisegundos (`walk_amplitudes`).

**Qué se ve.** A diferencia de una difusión clásica, el walk avanza de forma balística (la dispersión crece $\propto t$) y presenta interferencia: hay neuronas que se encienden y se apagan, y zonas que quedan oscuras porque las amplitudes de distintos caminos se cancelan. Desde AVM, la excitación alcanza ALML en $t\approx5.5$ y AVDL en $t\approx6.5$. Hacia $t = 60$ está repartida en una "participación efectiva" $1/\sum_k q_k^2 \approx 130$ neuronas.

---

## 4. El láser optogenético como rotación de Rabi

*Módulos:* `hamiltonian.laser_state`, `circuits/builders.laser`

En la channelrhodopsina, un pulso de luz resonante de frecuencia de Rabi $\Omega$ y duración $\tau$ rota un sistema de dos niveles en un ángulo $\theta = \Omega\tau$. En un qubit, el mismo control es

$$
R_X(\theta) = e^{-i\theta X/2},\qquad
R_X(\theta)|0\rangle = \cos\tfrac{\theta}{2}|0\rangle - i\sin\tfrac{\theta}{2}|1\rangle .
$$

Al iluminar la neurona $j$ de la red en reposo:

$$
|\psi(0)\rangle = \cos\tfrac{\theta}{2}\,|0\cdots0\rangle - i\sin\tfrac{\theta}{2}\,|e_j\rangle .
$$

Por las propiedades 2 y 3 de §3, el vacío no evoluciona y la componente excitada hace el quantum walk:

$$
|\psi(t)\rangle = \cos\tfrac{\theta}{2}\,|0\cdots0\rangle - i\sin\tfrac{\theta}{2}\sum_k \big[e^{-i\gamma Jt}\big]_{kj}|e_k\rangle .
$$

**Resultado central (probabilidad de disparo de la neurona $k$):**

$$
\boxed{\,P_k(t) = \sin^2\!\tfrac{\theta}{2}\;\Big|\big[e^{-i\gamma Jt}\big]_{kj}\Big|^2\,}
$$

La intensidad del láser sólo escala la amplitud global: con $\theta = \pi$ el disparo es seguro, y con $\theta=\pi/2$ ocurre la mitad de las veces. El *patrón* de propagación lo fija el conectoma. `test_xy_single_excitation_equals_ctqw` y `test_vacuum_probability_is_cos2` verifican esta fórmula contra la evolución exacta en el espacio de Hilbert completo.

**Varios láseres.** $\bigotimes_{s\in S}R_X(\theta)_s$ crea una superposición de sectores con $0,\dots,|S|$ excitaciones (pesos binomiales). Para $|S|\ge2$ la dinámica ya no se reduce a $J$: la exclusión de núcleo duro impide que dos excitaciones ocupen la misma neurona. El backend la resuelve de forma exacta en el espacio completo para microcircuitos (`evolve_exact`, $n\le16$).

---

## 5. Medición: el spike y la ley de conservación

Se mide cada qubit en la base $Z$. Un disparo (*shot*) devuelve una cadena de bits, que es un patrón de activación del microcircuito: el bit $k$ en 1 significa que la neurona $k$ disparó. La población $P_k = \Pr[b_k = 1]$ es la marginal.

Como $\hat N$ se conserva, con $k$ láseres **ningún disparo ideal puede tener más de $k$ bits en 1**. Esa regla es la base de la mitigación por post-selección (§8).

---

## 6. Del hamiltoniano al circuito en IonQ

*Módulos:* `circuits/builders.py`, `circuits/compile_ionq.py` · *Tests:* `test_trotter.py`, `test_compilation.py`

### 6.1 Por qué IonQ

- **Conectividad total (all-to-all).** Cualquier par de iones puede entrelazarse directamente. Un conectoma es un grafo irregular y no planar, así que en un chip de vecinos cercanos cada sinapsis requeriría cadenas de SWAP. En IonQ cada sinapsis es una compuerta directa, sin sobrecosto de ruteo.
- **Compuerta de entrelazamiento parametrizada.** Forte expone $ZZ(\theta)$ con el ángulo como parámetro, lo que encaja con los saltos pequeños $\gamma J_{ij}\delta t$ de una fórmula de Trotter. Los ángulos se reducen a $[0, \tfrac14]$ (§6.4).
- **Calidad.** Forte tiene 36 qubits, fidelidad de 1 qubit de 99,98 % y de 2 qubits de 99,6 % (ionq.com/quantum-systems/compare).

### 6.2 Evolución por Trotter–Suzuki (modo `trotter`)

Escribimos $H = \sum_{e} h_e$, con un término por sinapsis, $h_e = \gamma J_e\,(XX+YY)/2$. Cada término se exponencia exactamente con la compuerta de salto

$$
\mathrm{hop}(\alpha) \equiv e^{-i\alpha (XX+YY)/2},\qquad e^{-ih_e\delta} = \mathrm{hop}(\gamma J_e\delta).
$$

**1er orden:** $U_1(\delta) = \prod_e e^{-ih_e\delta}$. **2º orden (Strang):** $U_2(\delta) = \prod_e e^{-ih_e\delta/2}\prod_{e\,\text{(reverso)}} e^{-ih_e\delta/2}$. Con $r$ pasos y $\delta=t/r$:

$$
\big\|e^{-iHt} - U_1(t/r)^r\big\| \le \frac{t^2}{2r}\sum_{a<b}\big\|[h_a,h_b]\big\|,
\qquad
\big\|e^{-iHt} - U_2(t/r)^r\big\| = O\!\left(\frac{t^3}{r^2}\right)
$$

(Childs et al. 2021). Las mitades consecutivas sobre el mismo par se fusionan exactamente, porque un término conmuta consigo mismo. Así, $r$ pasos de 2º orden cuestan $(2|E|-2)\,r + 1$ saltos y no $2|E|r$; en `toque-6` ($|E|=8$, $r=2$) son 29 saltos, o sea 58 ZZ. La cota de conmutadores es holgada: en `toque-6`, a $t=30$ con $r=2$, la cota de 1er orden vale 7, mientras que el error real de 2º orden en distribución es TVD = 0,09. `test_trotter.py` comprueba numéricamente que el error escala como $1/r$ y $1/r^2$.

Al usar el hamiltoniano real, este modo es una **simulación hamiltoniana genuina** (Lloyd 1996) y se generaliza tal cual a varios láseres.

### 6.3 Modo compilado por rotaciones de Givens (modo `givens`)

Con un solo láser, el estado final es $\cos\frac{\theta}{2}|0\rangle - i\sin\frac{\theta}{2}\sum_k v_k|e_k\rangle$, con $v = e^{-i\gamma Jt}e_j$, que se calcula clásicamente. Una cascada de $n-1$ saltos prepara un vector con los módulos $|v_k|$ exactos sin tocar el vacío (Kivlichan et al. 2018; Jiang et al. 2018):

$$
\cos\alpha_m = \frac{|v_{o_m}|}{R_m},\qquad R_{m+1} = R_m\sin\alpha_m,\qquad R_0 = 1,
$$

donde $o_0 = j$ y $o_1,o_2,\dots$ son las demás neuronas. $\mathrm{hop}(\alpha)$ lleva $|10\rangle\mapsto\cos\alpha|10\rangle - i\sin\alpha|01\rangle$.

- **Ventaja:** profundidad mínima ($n-1$ saltos) y distribución en base $Z$ exacta.
- **Desventaja (honesta):** requiere conocer la respuesta de antemano, así que no es simulación cuántica. Sirve para validar la lectura del hardware y para la demo en microcircuitos grandes, donde Trotter es demasiado profundo. Las fases no se reproducen porque no afectan la medición en $Z$.

### 6.4 Compilación a compuertas nativas de IonQ Forte

IonQ define (fases en *vueltas*, 1 vuelta = $2\pi$; docs.ionq.com, *Getting started with native gates*):

$$
\mathrm{GPi}(\phi)=\begin{pmatrix}0&e^{-2\pi i\phi}\\ e^{2\pi i\phi}&0\end{pmatrix},\quad
\mathrm{GPi2}(\phi)=\tfrac{1}{\sqrt2}\begin{pmatrix}1&-ie^{-2\pi i\phi}\\ -ie^{2\pi i\phi}&1\end{pmatrix},\quad
ZZ(\theta)=e^{-i\pi\theta\,Z\otimes Z}.
$$

$Z$ es virtual: se absorbe en las fases de las compuertas siguientes. Derivación de cada pieza:

**Salto.** $XX$ y $YY$ conmutan, por lo que $\mathrm{hop}(\alpha) = e^{-i\frac{\alpha}{2}XX}\,e^{-i\frac{\alpha}{2}YY}$. Con un cambio de base local:

$$
e^{-i\beta XX} = (V\!\otimes\! V)\,ZZ\!\left(\tfrac{\beta}{\pi}\right)(V^\dagger\!\otimes\! V^\dagger),\quad V=\mathrm{GPi2}(\tfrac14)=R_Y(\tfrac{\pi}{2}),\ V Z V^\dagger = X,
$$

$$
e^{-i\beta YY} = (W\!\otimes\! W)\,ZZ\!\left(\tfrac{\beta}{\pi}\right)(W^\dagger\!\otimes\! W^\dagger),\quad W=\mathrm{GPi2}(0)=R_X(\tfrac{\pi}{2}),\ W Z W^\dagger = -Y .
$$

⇒ **cada sinapsis por paso cuesta exactamente 2 compuertas ZZ**. Es el mínimo para una compuerta con dos coeficientes de Cartan no nulos.

**Láser.** $R_X(\theta) = \mathrm{GPi2}(\tfrac14)\,R_Z(\theta)\,\mathrm{GPi2}(\tfrac34)$.

**Reducción del ángulo ZZ a $[0, \tfrac14]$**, con identidades exactas:

- $ZZ(\theta+1) = -ZZ(\theta)$
- $ZZ(\theta+\tfrac12) = -i\,(Z\otimes Z)\,ZZ(\theta)$, donde $Z\otimes Z$ es virtual
- $ZZ(-\theta) = (X\otimes I)\,ZZ(\theta)\,(X\otimes I)$ con $X \cong \mathrm{GPi}(0)$

**Re-síntesis de 1 qubit.** Cada racha de compuertas de 1 qubit entre dos ZZ se multiplica y se re-escribe con la descomposición de Euler $R_Z R_Y R_Z$, usando $R_Y(b) = R_X(\tfrac{\pi}{2})R_Z(-b)R_X(-\tfrac{\pi}{2})$. Así queda en **≤ 2 pulsos GPi2** (0 si es diagonal, 1 si $b=\pm\pi/2$ ó $\pi$). En `toque-6` esto reduce las GPi2 de 232 a 122.

**Propagación de Z virtual.** $\mathrm{GPi2}(\phi)\,R_Z(\theta) = R_Z(\theta)\,\mathrm{GPi2}(\phi - \tfrac{\theta}{2\pi})$, y lo mismo para GPi. $ZZ$ conmuta con $Z$. Se empujan todas las $R_Z$ al final del circuito, donde no afectan la medición en $Z$. El resultado contiene sólo `gpi`, `gpi2` y `zz`, que es el formato `gateset: "native"` de la API.

**Alternativas incluidas.**

- `target="aria"`: $e^{-i\beta XX} = \mathrm{MS}(0,0,\beta/\pi)$ y $e^{-i\beta YY} = \mathrm{MS}(\tfrac14,\tfrac14,\beta/\pi)$, con MS parcial.
- `gateset="qis"`: $e^{-i\beta ZZ} = \mathrm{CNOT}\,(I\otimes R_Z(2\beta))\,\mathrm{CNOT}$, para que IonQ compile en su servidor.
- Exportación a OpenQASM 2.0, para usar el mismo circuito en Qiskit o Braket.

Todas las identidades se verifican matriz por matriz en `test_compilation.py`.

### 6.5 Envío a IonQ

`cerebro/ionq/client.py` habla directamente con la API REST v0.4, sin depender de SDKs:

```
POST https://api.ionq.co/v0.4/jobs
Authorization: apiKey <IONQ_API_KEY>
{ "type": "ionq.circuit.v1", "backend": "simulator" | "qpu.forte-1",
  "noise": {"model": "forte-1"},           ← sólo simulador
  "shots": 1000,
  "input": { "qubits": 6, "gateset": "native", "circuit": [ {"gate":"gpi2","target":0,"phase":0.75}, {"gate":"zz","targets":[0,1],"angle":0.0137}, … ] } }
GET  /v0.4/jobs/{id}                       → estado
GET  /v0.4/jobs/{id}/results/probabilities → {"<entero>": prob}
```

Antes de interpretar resultados se corre un circuito de calibración gratuito ($X$ en $q_0$, simulador ideal) para confirmar que el qubit 0 es el bit menos significativo de las claves.

---

## 7. Presupuesto de errores y elección de parámetros

*Módulo:* `pipeline.autotune_steps` · *Script:* `scripts/resource_report.py`

Hay dos fuentes de error que compiten:

- **Algorítmico** (Trotter): disminuye con más pasos, $\varepsilon_T(r) = O(t^3/r^2)$.
- **Hardware**: aumenta con el número de compuertas. A primer orden, la probabilidad de que ninguna falle es $F_{hw}(r) \approx f_{2q}^{\,N_{ZZ}(r)}\,f_{1q}^{\,N_{1q}(r)}$, con $f_{2q}=0.996$ y $f_{1q}=0.9998$ (Forte).

El backend elige $r^* = \arg\min_r\big[\mathrm{TVD}_{\text{Trotter}}(r) + (1 - F_{hw}(r))\big]$, calculando el primer término exactamente para el microcircuito. Resultado para $t = 30$, láser $\theta=\pi$ en AVM (salida de `resource_report.py`):

| Microcircuito | qubits | sinapsis | $r^*$ | ZZ (Trotter) | GPi2 | $F_{hw}$ | TVD Trotter | ZZ (Givens) | $F_{hw}$ Givens |
|---|---|---|---|---|---|---|---|---|---|
| toque-6 | 6 | 8 | 2 | 58 | 122 | 0.77 | 0.093 | 10 | 0.96 |
| toque-7 | 7 | 11 | 2 | 82 | 171 | 0.70 | 0.179 | 12 | 0.95 |
| toque-bilateral-10 | 10 | 25 | 1 | 98 | 206 | 0.65 | 0.262 | 18 | 0.92 |
| toque-14 | 14 | 44 | 1 | 174 | 362 | 0.46 | 0.412 | 26 | 0.89 |

**Lectura:**

- `toque-6` con Trotter de 2º orden y $r=2$ es el experimento recomendado para hardware: es una simulación hamiltoniana genuina con ~77 % de probabilidad de no tener errores de compuerta.
- Para 10–14 neuronas, Trotter queda dominado por el error algorítmico o por el ruido. El modo Givens mantiene la fidelidad sobre 0,89 y permite mostrar el circuito completo en hardware.

El simulador local (`circuits/simulator.noisy_probabilities`) usa este mismo modelo: un canal despolarizante tras cada compuerta física (Pauli aleatorio por trayectoria de Monte Carlo) y error de lectura simétrico de 0,5 %. Sirve para ensayar la demo sin conexión.

El estimador es estratificado. El término sin errores, de peso $P_0=\prod_i(1-p_i)$, se suma de forma exacta como la distribución ideal. Las trayectorias se condicionan a tener al menos un error: el primero se muestrea de $q_i = p_i\prod_{j<i}(1-p_j)/(1-P_0)$ y la simulación arranca desde el estado ideal ya calculado tras la compuerta $i$. La esperanza es idéntica a la de Monte Carlo simple, con menor varianza y unas 7 veces menos cómputo. `test_matches_density_matrix` lo compara contra la evolución exacta de la matriz densidad.

---

## 8. Mitigación de errores y protocolo experimental

1. **Post-selección por simetría** (Bonet-Monroig et al. 2018; McArdle et al. 2019). Se descartan los disparos con más excitaciones que láseres y se renormaliza (`analysis.postselect`). En el simulador local con ruido Forte, para `toque-6`, la TVD respecto de la teoría baja de 0,24 a 0,12 tras post-seleccionar. Este procedimiento es exactamente el que IonQ recomienda como *symmetry-based post-selection* en su guía de buenas prácticas.
2. **Mismo número de pasos de Trotter en todos los tiempos.** IonQ lo recomienda porque deja un error experimental homogéneo, más fácil de corregir. El script de experimento lo impone (`--steps` fijo).
3. **Debiasing de IonQ.** El servidor puede generar variantes simétricas del circuito y agregarlas; queda disponible vía `settings.error_mitigation` en la API.
4. **Validación cruzada.** Para cada tiempo se comparan cuatro curvas: (i) teoría exacta, (ii) circuito ideal (sólo error de Trotter), (iii) simulador de IonQ con modelo de ruido `forte-1` y (iv) QPU. La diferencia entre (i) y (ii) es algorítmica, y entre (ii) y (iv) es de hardware.

**Protocolo sugerido para la hackathon** (`scripts/run_ionq_experiment.py`):

```
python scripts/run_ionq_experiment.py --dry-run                       # recursos, sin enviar
python scripts/run_ionq_experiment.py --backend simulator --noise forte-1 --times 10 20 30 40
python scripts/run_ionq_experiment.py --backend qpu.forte-1 --times 10 20 30 40 --shots 500   # ALLOW_QPU=true
```

---

## 9. Verificación numérica implementada

`python -m unittest discover -s tests` (o `pytest`) corre 28 pruebas:

| Afirmación de la teoría | Test |
|---|---|
| $J$ simétrica, $\|J\|_2 = 1$, 302 neuronas | `test_physics.TestConnectome` |
| Sector de 1 excitación de XY = quantum walk $\gamma J$ | `test_xy_single_excitation_equals_ctqw` |
| $P(\text{vacío}) = \cos^2(\theta/2)$ para todo $t$ | `test_vacuum_probability_is_cos2` |
| $[H,\hat N]=0$ y $H=H^\dagger$ | `test_excitation_number_conserved` |
| Matrices nativas = definiciones de IonQ | `test_ionq_matrices_from_docs` |
| hop → 2 ZZ (Forte), 2 MS (Aria), CNOT (qis) exactos | `test_hop_forte_aria_qis` |
| Propagación de Z virtual exacta | `test_virtual_z_propagation` |
| Re-síntesis con ≤ 2 GPi2 | `test_single_qubit_synthesis` |
| Error de Trotter $\propto 1/r$ y $1/r^2$ | `test_first_order_scaling`, `test_second_order_scaling` |
| Givens reproduce la distribución exacta con ≤ n−1 saltos | `test_givens_reproduces_distribution` |
| El simulador con ruido reproduce el canal despolarizante exacto (matriz densidad) | `test_matches_density_matrix` |
| Flujo completo API ↔ IonQ (servidor simulado) | `test_ionq_flow` |

---

## 10. Extensiones posibles

- **Sinapsis dirigidas.** Un hamiltoniano no puede ser asimétrico. Las opciones son una caminata cuántica estocástica, que interpola con la clásica mediante una ecuación de Lindblad (Whitfield et al. 2010), o fases complejas $J_{ij}e^{i\varphi_{ij}}$ que rompen la simetría de inversión temporal (*chiral quantum walks*, Zimborás et al. 2013).
- **Inhibición.** Las sinapsis GABAérgicas podrían llevar un signo negativo en $J_{ij}$. El circuito no cambia, porque la compilación ya admite ángulos negativos.
- **Varios láseres en hardware.** Es el régimen de muchos cuerpos, clásicamente costoso, donde la simulación cuántica tiene sentido real.
- **Disipación.** Un *amplitude damping* controlado modelaría el retorno al reposo de la neurona.

---

## 11. Referencias

1. E. Farhi, S. Gutmann, *Quantum computation and decision trees*, Phys. Rev. A **58**, 915 (1998).
2. A. M. Childs, *Universal computation by quantum walk*, Phys. Rev. Lett. **102**, 180501 (2009).
3. O. Mülken, A. Blumen, *Continuous-time quantum walks: Models for coherent transport on complex networks*, Phys. Rep. **502**, 37 (2011).
4. S. J. Cook et al., *Whole-animal connectomes of both Caenorhabditis elegans sexes*, Nature **571**, 63 (2019).
5. J. G. White et al., *The structure of the nervous system of the nematode C. elegans*, Phil. Trans. R. Soc. B **314**, 1 (1986).
6. M. Chalfie et al., *The neural circuit for touch sensitivity in Caenorhabditis elegans*, J. Neurosci. **5**, 956 (1985).
7. G. Nagel et al., *Light activation of channelrhodopsin-2 in excitable cells of Caenorhabditis elegans triggers rapid behavioral responses*, Curr. Biol. **15**, 2279 (2005).
8. E. S. Boyden et al., *Millisecond-timescale, genetically targeted optical control of neural activity*, Nat. Neurosci. **8**, 1263 (2005).
9. S. Lloyd, *Universal quantum simulators*, Science **273**, 1073 (1996).
10. A. M. Childs, Y. Su, M. C. Tran, N. Wiebe, S. Zhu, *Theory of Trotter error with commutator scaling*, Phys. Rev. X **11**, 011020 (2021).
11. A. Sørensen, K. Mølmer, *Quantum computation with ions in thermal motion*, Phys. Rev. Lett. **82**, 1971 (1999).
12. I. D. Kivlichan et al., *Quantum simulation of electronic structure with linear depth and connectivity*, Phys. Rev. Lett. **120**, 110501 (2018).
13. Z. Jiang et al., *Quantum algorithms to simulate many-body physics of correlated fermions*, Phys. Rev. Applied **9**, 044036 (2018).
14. X. Bonet-Monroig, R. Sagastizabal, M. Singh, T. E. O'Brien, *Low-cost error mitigation by symmetry verification*, Phys. Rev. A **98**, 062339 (2018).
15. S. McArdle, X. Yuan, S. Benjamin, *Error-mitigated digital quantum simulation*, Phys. Rev. Lett. **122**, 180501 (2019).
16. S. Bose, *Quantum communication through an unmodulated spin chain*, Phys. Rev. Lett. **91**, 207901 (2003).
17. J. D. Whitfield, C. A. Rodríguez-Rosario, A. Aspuru-Guzik, *Quantum stochastic walks*, Phys. Rev. A **81**, 022323 (2010).
18. Z. Zimborás et al., *Quantum transport enhancement by time-reversal symmetry breaking*, Sci. Rep. **3**, 2361 (2013).
19. IonQ, *Getting started with native gates*: https://docs.ionq.com/guides/getting-started-with-native-gates
20. IonQ, *API v0.4 — Create job*: https://docs.ionq.com/api-reference/v0.4/jobs/create-job
21. IonQ, *Best practices for using IonQ hardware*: https://ionq.com/docs/best-practices-for-using-ionq-hardware
22. IonQ, *Compare quantum systems*: https://www.ionq.com/quantum-systems/compare
23. OpenWorm: https://github.com/openworm/c302 y https://github.com/openworm/CElegansNeuroML
