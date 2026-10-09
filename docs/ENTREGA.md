# Checklist de entrega · Qollab × IonQ Quantum Hackathon

Fuentes: [bases](https://qollab.xyz/programs/hackathon/terms), [cómo funciona](https://qollab.xyz/programs/hackathon/how-it-works) y [entorno de ejecución de Qollab](https://qollab.xyz/learn/docs/runtime-environment). Revisado el 9 oct. 2026.

**Ventana de construcción:** viernes 9 oct., 20:00 → domingo 11 oct., 20:00 (hora de Chile). En ET es 19:00 → 19:00. La entrega cierra al final de la ventana y el capitán puede editarla hasta ese momento.

## Requisitos obligatorios

| # | Requisito (bases) | Estado | Qué falta |
| --- | --- | --- | --- |
| 1 | Usar **Qiskit** | ❌ | El núcleo usa numpy y la API REST de IonQ. Hay que construir y ejecutar los circuitos con `qiskit.QuantumCircuit` |
| 2 | **Publicado y ejecutable en Qollab.xyz** (corre en sus simuladores gratuitos, incluido el de IonQ) | ❌ | Crear un proyecto *JS / Qiskit wrapper* en Qollab (ver "Plan de port" abajo) |
| 3 | **Licencia MIT** (proyecto y repos externos de los que dependa) | ✅ | `LICENSE` agregado |
| 4 | Repo **público**, sin claves, dependencias listadas | ✅ | `backend/.env` está en `.gitignore`; `requirements.txt` existe |
| 5 | **Página del proyecto en Qollab**: qué hace, qué problema aborda, cómo correrlo, cómo replicarlo y extenderlo | ⏳ | Redactar el *Project Card* en Markdown (base: README + `docs/TEORIA.md` §1) |
| 6 | **Video demo de 2–3 min**, link público sin login (YouTube, Loom, Vimeo o Drive) | ⏳ | Grabación de pantalla con voz; puede incluir el render de Blender |
| 7 | **Construido durante la ventana**; el trabajo previo se permite si se **declara** | ⚠️ | Sección de divulgación ya en el README. Falta etiquetar `pre-hackathon` y declararlo también en la página de Qollab |
| 8 | Línea **"This effort is supported by Qollab & IonQ."** | ✅ | En el README; repetirla en la página de Qollab |
| 9 | **Buenas prácticas de accesibilidad en la UI** | ⚠️ | Etiquetas ARIA, navegación por teclado, contraste, `prefers-reduced-motion`, alternativa textual al canvas 3D |
| 10 | Superar el nivel tutorial (aplicación nueva, extensión técnica u aporte educativo original) | ✅ | Aplicación nueva (conectoma real), extensión técnica (post-selección, benchmarking Trotter vs. ruido) y aporte educativo |
| 11 | Entregar con el **formulario** de la página de registro (el capitán) | ⏳ | Al final; se puede editar hasta el cierre |

**Riesgo principal:** presentar trabajo previo como nuevo es causa de descalificación. El jurado puntúa lo que se agrega dentro de la ventana, así que conviene que el port a Qiskit y Qollab, la accesibilidad, el video y los experimentos se hagan *durante* la ventana y queden en commits fechados.

## Tema y criterios

- **Tema recomendado: Quantum Unlocked.** Enseña simulación hamiltoniana, Trotterización, compilación a hardware y mitigación por simetría con un demo interactivo. También encaja en *Quantum Playground*, porque la interferencia del walk es lo que se ve. Un proyecto puede declarar uno o más temas.
- **Rúbrica** (sin pesos publicados): Novedad y creatividad · Ejecución técnica · Potencial de impacto · Calidad de documentación. También hay premio a la mejor documentación, donde `docs/TEORIA.md` es un punto fuerte.

## Plan de port a Qollab (proyecto *JS / Qiskit wrapper*)

Qollab ejecuta todo en el navegador: Python en Pyodide (con numpy, scipy y Qiskit ≥ 2.5) y la página JS en un iframe. Consecuencias para este proyecto:

| Hoy | En Qollab |
| --- | --- |
| Servidor Starlette + `fetch('/api/…')` | No hay servidor (sólo se permite GET hacia afuera). `main.js` importa módulos Python y los llama con `.callPromising(...)` |
| `api.js` (HTTP) | Nuevo adaptador `qollab.js` con las mismas funciones (`walk`, `simulate`, …) que llama a Python |
| Circuitos en IR propio + REST de IonQ | `qiskit.QuantumCircuit` (RX + `XXPlusYYGate`/RXX+RYY) ejecutado con el `backend` que elige quien presiona *Run*: simulador ideal, simuladores de IonQ con ruido o Forte |
| Varias corridas por ejecución | **IonQ acepta un solo job por ejecución**: un circuito (un tiempo t) por corrida en IonQ; en el simulador local se pueden barrer varios |
| three.js r170 vendorizado | Qollab trae `three` 0.186.1 importable por nombre (se borra `vendor/`) |
| `fetch` de `gusano.glb` | JS no puede leer archivos del proyecto: Python lee el `.glb` y se lo pasa a JS (o se usa el cuerpo procedural) |
| Rutas `DATA_DIR / "x"` | Las rutas de datos deben estar escritas literalmente (`"data/neurons.json"`) para que Qollab las cargue |
| `localStorage` | No disponible; la preferencia de calidad queda en memoria (ya está protegida con try/catch) |
| Límites | ≤ 100 archivos de ≤ 2 MB cada uno |

El backend local (Starlette) se mantiene en el repo como alternativa para desarrollo y para el script de experimentos en IonQ por API.

## Video (2–3 min), guion sugerido

| Tiempo | Contenido |
| --- | --- |
| 0:00–0:20 | Gancho: la luz enciende neuronas (optogenética) y pulsos rotan qubits. Render de Blender |
| 0:20–0:55 | La idea: conectoma real de 302 neuronas → hamiltoniano XY → quantum walk. Demo: clic-láser y propagación |
| 0:55–1:40 | Hardware: microcircuito del toque compilado para IonQ; teoría vs. Trotter vs. simulador de IonQ con ruido; post-selección |
| 1:40–2:20 | Corrida en Qollab con el backend de IonQ y resultado en vivo |
| 2:20–2:45 | Qué aprendimos, límites honestos, cómo extenderlo. Créditos + "supported by Qollab & IonQ" |
