// Cerebro Cuántico Optogenético · página Qollab (JS / Qiskit)
//
//  1. Láser → quantum walk exacto sobre las 302 neuronas (Python/numpy, sin backend).
//  2. Microcircuito → circuito Qiskit (RX + RXX·RYY) → simulación local con teoría, ideal y ruido.
//  3. "Ejecutar circuito" → UN job en el `backend` que eligió quien presionó Run
//     (simulador integrado, simuladores con ruido de IBM o IonQ, o el hardware IonQ Forte).
//
// This effort is supported by Qollab & IonQ.
import { QUALITY, WormScene } from "./js/escena.js";
import { dataTable, groupedBars, SERIES_COLORS, timeSeries } from "./js/graficos.js";
import { py, respirar } from "./js/python.js";

const $ = (id) => document.getElementById(id);
const TYPE_ES = { sensory: "sensorial", interneuron: "interneurona", motor: "motora", unknown: "—" };
const REDUCED = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
// Qollab crea `backend` antes de correr main.js (no se elige ni se escribe en el código).
const BACKEND = typeof backend !== "undefined" ? backend : null; // eslint-disable-line no-undef

const state = {
  neurons: [],
  index: new Map(),
  source: "AVM",
  walk: null,
  frame: 0,
  playing: false,
  presets: [],
  preset: "toque-6",
  mode: "trotter",
  micro: null,
  medido: null,
  backend: null,
  jobsSent: 0,
  armedHardware: false,
};

const scene = new WormScene($("scene"), { quality: "auto" });

// ------------------------------------------------------------------ utilidades
function toast(msg, isErr = false) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.toggle("err", isErr);
  t.classList.add("show");
  clearTimeout(toast._h);
  toast._h = setTimeout(() => t.classList.remove("show"), isErr ? 7000 : 3500);
}
function announce(msg) {
  const s = $("sr-status");
  s.textContent = "";
  setTimeout(() => { s.textContent = msg; }, 30);
}
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtTheta = (th) => (Math.abs(th - Math.PI) < 0.01 ? "π" : `${(th / Math.PI).toFixed(2)}π`);
const pct = (v) => `${(100 * v).toFixed(1)}%`;
const params = () => ({
  theta: parseFloat($("theta").value),
  gamma: parseFloat($("gamma").value),
  t_max: parseFloat($("tmax").value),
});
const modo = () => document.querySelector('input[name="modo"]:checked').value;

function neuronCard(name) {
  const i = state.index.get(name);
  if (i == null) { $("neuron-card").textContent = "Neurona no encontrada"; return; }
  const d = state.neurons[i];
  const nt = d.neurotransmitters?.length ? d.neurotransmitters.join(", ") : "—";
  $("neuron-card").innerHTML =
    `<b>${esc(d.name)}</b><span class="tag ${d.type}">${TYPE_ES[d.type]}</span><br>` +
    `${d.degree} conexiones · neurotransmisor: ${esc(nt)}<br>` +
    `posición anteroposterior: ${d.y.toFixed(0)} µm`;
}

// ------------------------------------------------------------------ 1 · láser
async function fire(name = $("neuron-input").value.trim().toUpperCase()) {
  if (!state.index.has(name)) { toast(`No existe la neurona "${name}"`, true); return; }
  state.source = name;
  $("neuron-input").value = name;
  neuronCard(name);
  const idx = state.index.get(name);
  const p = params();
  $("fire-btn").disabled = true;
  scene.setLabel(idx, `⚡ ${name}`);
  scene.fireLaser(idx, Math.sin(p.theta / 2) ** 2);
  await respirar();
  try {
    state.walk = await py.walk({ fuente: name, theta: p.theta, gamma: p.gamma, t_max: p.t_max, cuadros: 160 });
    state.frame = 0;
    describeWalk();
    if (REDUCED) {
      // Sin animación automática: se muestra un instante intermedio y se reproduce a pedido.
      state.frame = Math.round((state.walk.prob.length - 1) * 0.3);
      renderFrame(true);
    } else {
      setTimeout(() => setPlaying(true), 450);
    }
    const pr = selectedPreset();
    if (pr && pr.neuronas.includes(name) && state.micro && state.micro.fuente !== name) compile();
  } catch (e) {
    toast(`Error en Python: ${e.message}`, true);
  } finally {
    $("fire-btn").disabled = false;
  }
}

/** Texto para lectores de pantalla: qué neuronas terminan más activas. */
function describeWalk() {
  const W = state.walk;
  const last = W.prob[W.prob.length - 1];
  const order = Array.from(last.keys()).sort((a, b) => last[b] - last[a]).slice(0, 3);
  const top = order.map((k) => `${state.neurons[k].name} ${pct(last[k])}`).join(", ");
  const msg = `Láser en ${W.source}, probabilidad de disparo ${pct(W.fire_probability)}. ` +
    `Al final de la simulación las neuronas más probables son: ${top}.`;
  $("scene").setAttribute("aria-label", `Gusano C. elegans en 3D. ${msg}`);
  announce(msg);
}

function setPlaying(v) {
  state.playing = v;
  scene.setContinuous(v);
  $("play-btn").setAttribute("aria-pressed", String(v));
  $("play-btn").setAttribute("aria-label", v ? "Pausar" : "Reproducir");
  $("play-icon").innerHTML = v ? '<path d="M7 5h4v14H7zM13 5h4v14h-4z"/>' : '<path d="M7 5l12 7-12 7z"/>';
}

let _P = null;
function frameValues(f) {
  const W = state.walk;
  const n = W.prob.length;
  const i0 = Math.min(n - 1, Math.floor(f)), i1 = Math.min(n - 1, i0 + 1), a = f - i0;
  const r0 = W.prob[i0], r1 = W.prob[i1];
  if (!_P || _P.length !== r0.length) _P = new Float32Array(r0.length);
  for (let k = 0; k < _P.length; k++) _P[k] = r0[k] * (1 - a) + r1[k] * a;
  return { P: _P, t: W.times[i0] * (1 - a) + W.times[i1] * a, part: W.participation[i0] };
}

function renderFrame(force = false) {
  if (!state.walk) return;
  const { P, t, part } = frameValues(state.frame);
  const pfire = Math.max(state.walk.fire_probability, 1e-9);
  let max = 0, top = 0, active = 0;
  for (let k = 0; k < P.length; k++) {
    if (P[k] > max) { max = P[k]; top = k; }
    if (P[k] / pfire > 0.005) active++;
  }
  const rel = $("relative").checked;
  const vals = (renderFrame._vals ??= new Float32Array(P.length));
  for (let k = 0; k < P.length; k++) vals[k] = Math.min(1, rel ? P[k] / Math.max(max, 1e-12) : Math.sqrt(P[k] / pfire));
  scene.setActivity(vals);
  $("time-label").textContent = `t = ${t.toFixed(1)}`;
  // El DOM de texto se actualiza ~8 veces por segundo (la escena va a 60 fps)
  const now = performance.now();
  if (!force && state.playing && now - (renderFrame._lastUI ?? 0) < 120) return;
  renderFrame._lastUI = now;
  $("timeline").value = Math.round((1000 * state.frame) / (state.walk.prob.length - 1));
  $("timeline").setAttribute("aria-valuetext", `t = ${t.toFixed(1)}`);
  $("m-active").textContent = active;
  $("m-part").textContent = part.toFixed(1);
  $("m-top").textContent = state.neurons[top].name;
  const order = Array.from(P.keys()).sort((a, b) => P[b] - P[a]).slice(0, 6);
  $("toplist").innerHTML = order.map((k) => {
    const nm = state.neurons[k].name;
    return `<li><button type="button" data-n="${nm}" aria-label="${nm}: ${pct(P[k])}. Centrar la vista en ${nm}">` +
      `<span>${nm}</span><span class="bar" style="width:${(100 * P[k]) / Math.max(max, 1e-12)}%"></span>` +
      `<span class="p">${pct(P[k])}</span></button></li>`;
  }).join("");
}

let last = performance.now();
function loop(now) {
  const dt = (now - last) / 1000;
  last = now;
  if (state.playing && state.walk) {
    state.frame += dt * 16 * parseFloat($("speed").value);
    if (state.frame >= state.walk.prob.length - 1) {
      state.frame = state.walk.prob.length - 1;
      setPlaying(false);
      renderFrame(true);
    } else {
      renderFrame();
    }
  }
  requestAnimationFrame(loop);
}

function stepFrames(delta) {
  if (!state.walk) return;
  setPlaying(false);
  const n = state.walk.prob.length - 1;
  state.frame = Math.max(0, Math.min(n, Math.round(state.frame) + delta));
  renderFrame(true);
  const { P, t } = frameValues(state.frame);
  let top = 0;
  for (let k = 0; k < P.length; k++) if (P[k] > P[top]) top = k;
  announce(`t = ${t.toFixed(1)}; más probable ${state.neurons[top].name} con ${pct(P[top])}`);
}

// ------------------------------------------------------------------ 2 · microcircuito
function selectedPreset() { return state.presets.find((p) => p.id === state.preset); }

async function compile() {
  const pr = selectedPreset();
  if (!pr) return;
  const body = {
    preset: pr.id, fuente: pr.neuronas.includes(state.source) ? state.source : pr.fuente,
    theta: parseFloat($("theta").value), gamma: parseFloat($("gamma").value),
    t: parseFloat($("tmicro").value), modo: modo(), orden: 2,
  };
  const btn = $("compile-btn");
  btn.disabled = true;
  btn.textContent = "Calculando en Python…";
  await respirar();
  try {
    const r = await py.simular(body);
    state.micro = r;
    if (state.medido && state.medido.clave !== claveMicro(r)) state.medido = null;
    renderMicro();
    announce(`Microcircuito de ${r.n_qubits} qubits listo: ${r.recursos.compuertas_2q} compuertas de dos qubits, ` +
      `distancia a la teoría ${r.tvd_circuito.toFixed(3)}.`);
  } catch (e) {
    toast(`Error en Python: ${e.message}`, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Simular localmente (teoría · circuito · ruido)";
  }
}

const claveMicro = (r) => JSON.stringify([r.neuronas, r.fuente, r.theta, r.gamma, r.modo, r.pasos, r.t]);

function renderMicro() {
  const r = state.micro;
  if (!r) return;
  const res = r.recursos;
  const F = res.fidelidad_estimada;
  const m = state.medido;
  const fila = m ? m.resultados[m.resultados.length - 1] : null;
  $("chips").innerHTML = [
    `<span class="chip">qubits <b>${r.n_qubits}</b></span>`,
    `<span class="chip" title="Cada salto RXX·RYY se compila a una compuerta ZZ en IonQ Forte">2q <b>${res.compuertas_2q}</b></span>`,
    r.modo === "trotter" ? `<span class="chip">pasos <b>${r.pasos}</b></span>` : `<span class="chip">Givens <b>${r.saltos.length}</b></span>`,
    `<span class="chip ${F > 0.75 ? "good" : "warn"}" title="Fidelidad estimada en IonQ Forte">F<sub>Forte</sub> <b>${F.toFixed(2)}</b></span>`,
    `<span class="chip" title="Distancia de variación total entre circuito ideal y teoría exacta">TVD circuito <b>${r.tvd_circuito.toFixed(3)}</b></span>`,
    r.ruido ? `<span class="chip" title="Fracción de disparos que respeta la simetría (≤ 1 excitación)">aceptados <b>${pct(r.ruido.fraccion_aceptada)}</b></span>` : "",
    fila ? `<span class="chip good" title="TVD del backend tras post-selección">TVD backend <b>${fila.tvd_postseleccion.toFixed(3)}</b></span>` : "",
  ].join("");

  const labels = r.neuronas;
  const series = [
    { key: "exact", name: "Teoría exacta", values: r.exacta },
    { key: "ideal", name: "Circuito ideal", values: r.ideal },
  ];
  if (r.ruido) series.push({ key: "noisy", name: "Ruido tipo Forte (post-sel.)", values: r.ruido.marginales_postseleccion });
  if (fila) series.push({ key: "backend", name: `${m.backend} (post-sel.)`, values: fila.marginales_postseleccion });
  groupedBars($("bars"), labels, series, { highlight: [labels.indexOf(r.fuente)] });
  $("bars-legend").innerHTML = series.map((s) => `<span><i style="background:${SERIES_COLORS[s.key]}"></i>${esc(s.name)}</span>`).join("");
  dataTable($("bars-table"), labels, series, `Probabilidad de disparo por neurona en t = ${r.t}`);
  const puntos = m ? m.resultados.map((f) => ({ t: f.t, values: f.marginales_postseleccion })) : null;
  timeSeries($("series"), r.serie.tiempos, r.serie.marginales, labels, { marker: r.t, points: puntos });
  if (r.qiskit_texto) {
    $("qiskit-text").textContent = r.qiskit_texto;
    const ops = Object.entries(r.qiskit_ops || {}).map(([k, v]) => `${k}:${v}`).join(" ");
    $("circ-count").textContent = `· ${ops}`;
  } else {
    $("qiskit-text").textContent = "Qiskit no está disponible en este entorno.";
  }
  scene.setHighlight(labels.map((nm) => state.index.get(nm)).filter((i) => i != null));
}

// ------------------------------------------------------------------ 3 · backend
function renderBackendInfo() {
  const b = state.backend;
  const pill = $("backend-pill");
  if (!b) {
    pill.textContent = "sin backend";
    pill.className = "pill err";
    $("run-hint").textContent = "No hay backend: presiona Run en Qollab y elige uno.";
    $("run-btn").disabled = true;
    return;
  }
  pill.textContent = `backend: ${b.nombre}`;
  pill.className = `pill ${b.hardware ? "warn" : "ok"}`;
  $("run-hint").innerHTML = b.hardware
    ? `<b>${esc(b.nombre)}</b> es hardware real de IonQ: el job usa créditos. Pruébalo antes en el simulador remoto de Forte (gratis).`
    : b.ionq
      ? `<b>${esc(b.nombre)}</b>: simulador remoto de IonQ con su modelo de ruido (gratis). IonQ acepta <b>un job</b> por ejecución.`
      : `<b>${esc(b.nombre)}</b>: simulador local (gratis, sin límite de jobs).`;
}

async function runOnBackend() {
  if (!BACKEND || !state.backend) { toast("No hay backend: presiona Run en Qollab y elige uno.", true); return; }
  if (state.backend.ionq && state.jobsSent >= 1) {
    toast("IonQ acepta un solo job por ejecución: presiona Stop y luego Run para enviar otro.", true);
    return;
  }
  if (state.backend.hardware && !state.armedHardware) {
    state.armedHardware = true;
    $("run-btn").textContent = "Confirmar: enviar a hardware (usa créditos)";
    announce("Vuelve a presionar el botón para confirmar el envío al hardware.");
    return;
  }
  if (!state.micro) await compile();
  const r = state.micro;
  if (!r) return;
  const sweep = $("sweep").checked;
  const tiempos = sweep ? [0.25, 0.5, 0.75, 1].map((f) => Math.round(r.t * f * 100) / 100) : [r.t];
  const shots = Math.max(50, Math.min(5000, parseInt($("shots").value, 10) || 500));
  const btn = $("run-btn");
  btn.disabled = true;
  btn.textContent = `Ejecutando ${tiempos.length} circuito${tiempos.length > 1 ? "s" : ""} en un job…`;
  $("run-result").innerHTML = `<p class="result">Esperando resultados de <b>${esc(state.backend.nombre)}</b>…</p>`;
  await respirar();
  try {
    const m = await py.ejecutar(BACKEND, {
      preset: state.preset, fuente: r.fuente, theta: r.theta, gamma: r.gamma, modo: r.modo,
      pasos: r.pasos, orden: r.orden, tiempos, shots,
    });
    state.jobsSent++;
    m.clave = claveMicro(r);
    state.medido = m;
    renderMicro();
    renderRunResult(m);
    const f = m.resultados[m.resultados.length - 1];
    announce(`Resultados de ${m.backend}: distancia a la teoría ${f.tvd_postseleccion.toFixed(3)} tras post-selección, ` +
      `${pct(f.fraccion_aceptada)} de disparos aceptados.`);
  } catch (e) {
    $("run-result").innerHTML = `<p class="result">El job falló: ${esc(e.message)}</p>`;
    toast(`El job falló: ${e.message}`, true);
  } finally {
    state.armedHardware = false;
    btn.textContent = "Ejecutar circuito";
    btn.disabled = state.backend.ionq && state.jobsSent >= 1;
    if (btn.disabled) $("run-hint").innerHTML += " <b>Job enviado.</b> Para otro, presiona Stop y Run.";
  }
}

function renderRunResult(m) {
  const ops = (o) => Object.entries(o || {}).map(([k, v]) => `${k}:${v}`).join(" ") || "—";
  $("run-result").innerHTML =
    `<div class="result"><p><b>${esc(m.backend)}</b> · ${m.shots} disparos por circuito · ${m.modo}` +
    (m.modo === "trotter" ? ` · ${m.pasos} pasos` : "") + (m.job_id ? `<br>job <code>${esc(m.job_id)}</code>` : "") + `</p>` +
    `<div class="data-box"><table><caption class="sr-only">Comparación con la teoría por tiempo</caption>` +
    `<thead><tr><th scope="col">t</th><th scope="col">TVD bruto</th><th scope="col">TVD post-sel.</th><th scope="col">aceptados</th></tr></thead><tbody>` +
    m.resultados.map((f) => `<tr><th scope="row">${f.t}</th><td>${f.tvd_bruto.toFixed(3)}</td>` +
      `<td>${f.tvd_postseleccion.toFixed(3)}</td><td>${pct(f.fraccion_aceptada)}</td></tr>`).join("") +
    `</tbody></table></div>` +
    `<p class="hint">Compuertas escritas: <code>${esc(ops(m.ops_escritas))}</code><br>` +
    `Tras transpilar para el backend: <code>${esc(ops(m.ops_transpilado))}</code></p></div>`;
}

// ------------------------------------------------------------------ eventos
function bindUI() {
  $("fire-btn").addEventListener("click", () => fire());
  $("neuron-input").addEventListener("change", () => neuronCard($("neuron-input").value.trim().toUpperCase()));
  $("neuron-input").addEventListener("keydown", (e) => { if (e.key === "Enter") fire(); });
  $("theta").addEventListener("input", () => {
    const th = parseFloat($("theta").value);
    $("theta-val").textContent = fmtTheta(th);
    $("pfire").textContent = (Math.sin(th / 2) ** 2).toFixed(2);
    $("theta").setAttribute("aria-valuetext", `θ = ${fmtTheta(th)}, probabilidad de disparo ${(Math.sin(th / 2) ** 2).toFixed(2)}`);
  });
  $("gamma").addEventListener("input", () => { $("gamma-val").textContent = parseFloat($("gamma").value).toFixed(1); });
  $("tmax").addEventListener("input", () => { $("tmax-val").textContent = $("tmax").value; });
  $("tmicro").addEventListener("input", () => { $("tmicro-val").textContent = $("tmicro").value; });
  $("tmicro").addEventListener("change", compile);
  $("play-btn").addEventListener("click", () => {
    if (!state.walk) return;
    if (!state.playing && state.frame >= state.walk.prob.length - 1) state.frame = 0;
    setPlaying(!state.playing);
  });
  $("timeline").addEventListener("input", () => {
    if (!state.walk) return;
    setPlaying(false);
    state.frame = (parseInt($("timeline").value, 10) / 1000) * (state.walk.prob.length - 1);
    renderFrame(true);
  });
  $("relative").addEventListener("change", () => renderFrame(true));
  $("show-edges").addEventListener("change", () => scene.setEdgesVisible($("show-edges").checked));
  $("quality").addEventListener("change", () => scene.setQuality($("quality").value));
  scene.on("quality", (q, auto) => {
    $("quality").querySelector('option[value="auto"]').textContent = `Auto (${QUALITY[q].label.toLowerCase()})`;
    if (auto) toast(`Calidad gráfica ajustada a "${QUALITY[q].label}" para mantener la fluidez`);
  });
  $("autorotate").addEventListener("change", () => scene.setAutoRotate($("autorotate").checked));
  $("toplist").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-n]");
    if (b) scene.focus(state.index.get(b.dataset.n));
  });
  $("preset").addEventListener("change", () => {
    state.preset = $("preset").value;
    $("preset-desc").textContent = selectedPreset()?.descripcion ?? "";
    compile();
  });
  document.querySelectorAll('input[name="modo"]').forEach((r) => r.addEventListener("change", compile));
  $("compile-btn").addEventListener("click", compile);
  $("run-btn").addEventListener("click", runOnBackend);

  scene.on("key", (e) => {
    if (e.key === " " || e.key === "k") { $("play-btn").click(); return true; }
    if (e.key === "ArrowRight") { stepFrames(e.shiftKey ? 16 : 4); return true; }
    if (e.key === "ArrowLeft") { stepFrames(e.shiftKey ? -16 : -4); return true; }
    return false;
  });
  scene.on("pick", (i) => fire(state.neurons[i].name));
  const tip = $("tooltip");
  scene.on("hover", (i, px) => {
    if (i < 0 || !px) { tip.classList.remove("show"); return; }
    const d = state.neurons[i];
    let p = "";
    if (state.walk) p = `<br>P(disparo) = <b>${(100 * frameValues(state.frame).P[i]).toFixed(2)}%</b>`;
    tip.innerHTML = `<b>${d.name}</b> <span class="tag ${d.type}">${TYPE_ES[d.type]}</span><br>${d.degree} conexiones${p}` +
      `<br><span style="color:var(--faint)">clic: disparar láser aquí</span>`;
    tip.style.left = `${px[0] + 14}px`;
    tip.style.top = `${px[1] + 14}px`;
    tip.classList.add("show");
  });
}

// ------------------------------------------------------------------ arranque
async function init() {
  bindUI();
  requestAnimationFrame(loop);
  const loaderText = $("loader-text");
  try {
    loaderText.textContent = "Leyendo el conectoma de Cook et al. (2019) en Python…";
    await respirar();
    const con = await py.conectoma();
    state.neurons = con.neurons;
    con.neurons.forEach((d, i) => state.index.set(d.name, i));
    $("neuron-list").innerHTML = con.neurons.map((d) => `<option value="${d.name}">${TYPE_ES[d.type]}</option>`).join("");
    loaderText.textContent = "Cargando el cuerpo 3D…";
    let glb = null;
    try { glb = await py.cuerpo(); } catch (e) { console.log(`Sin cuerpo .glb: ${e.message}`); }
    scene.setData(con.neurons, con.edges, glb);

    const { microcircuitos } = await py.microcircuitos();
    state.presets = microcircuitos;
    $("preset").innerHTML = microcircuitos.map((m) =>
      `<option value="${m.id}">${esc(m.nombre)}${m.hardware ? " · recomendado para hardware" : ""}</option>`).join("");
    $("preset-desc").textContent = selectedPreset()?.descripcion ?? "";

    if (BACKEND) {
      try { state.backend = await py.backendInfo(BACKEND); } catch (e) { console.log(`backend: ${e.message}`); }
    }
    renderBackendInfo();
    $("loader").classList.add("hide");
    neuronCard(state.source);
    console.log(`Cerebro Cuántico Optogenético listo · ${con.neurons.length} neuronas · ${con.edges.length} sinapsis dibujadas` +
      (state.backend ? ` · backend ${state.backend.nombre}` : ""));
    await fire("AVM");
    await compile();
  } catch (e) {
    loaderText.textContent = `No se pudo iniciar el núcleo Python (${e.message}).`;
    $("backend-pill").textContent = "error";
    $("backend-pill").className = "pill err";
    console.log(`Error al iniciar: ${e.stack || e.message}`);
  }
}

await init();

// La página sigue siendo interactiva (láser, microcircuito, envío del job) hasta que se
// presione Stop: se mantiene viva la ejecución para que Python siga disponible.
await new Promise(() => {});
