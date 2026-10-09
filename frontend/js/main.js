// Orquestación de la interfaz: láser → quantum walk 3D, y microcircuito → IonQ.
import { api } from "./api.js";
import { QUALITY, WormScene } from "./scene.js";
import { circuitDiagram, groupedBars, SERIES_COLORS, timeSeries } from "./charts.js";

const $ = (id) => document.getElementById(id);
const TYPE_ES = { sensory: "sensorial", interneuron: "interneurona", motor: "motora", unknown: "—" };

const state = {
  health: null,
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
  ionqSeries: null,
};

const savedQuality = (() => { try { return localStorage.getItem("cerebro-calidad") || "auto"; } catch { return "auto"; } })();
const scene = new WormScene($("scene"), { quality: savedQuality });

// ------------------------------------------------------------------ utilidades
function toast(msg, isErr = false) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.toggle("err", isErr);
  t.classList.add("show");
  clearTimeout(toast._h);
  toast._h = setTimeout(() => t.classList.remove("show"), isErr ? 6000 : 3200);
}
const fmtTheta = (th) => (Math.abs(th - Math.PI) < 0.01 ? "π" : `${(th / Math.PI).toFixed(2)}π`);
const params = () => ({
  theta: parseFloat($("theta").value),
  gamma: parseFloat($("gamma").value),
  t_max: parseFloat($("tmax").value),
});

function neuronCard(name) {
  const i = state.index.get(name);
  if (i == null) { $("neuron-card").innerHTML = "Neurona no encontrada"; return; }
  const d = state.neurons[i];
  const nt = d.neurotransmitters?.length ? d.neurotransmitters.join(", ") : "—";
  $("neuron-card").innerHTML =
    `<b>${d.name}</b><span class="tag ${d.type}">${TYPE_ES[d.type]}</span><br>` +
    `${d.degree} conexiones · neurotransmisor: ${nt}<br>` +
    `posición anteroposterior: ${d.y.toFixed(0)} µm`;
}

// ------------------------------------------------------------------ láser
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
  try {
    const data = await api.walk({ source: name, theta: p.theta, gamma: p.gamma, t_max: p.t_max, frames: 160 });
    state.walk = data;
    state.frame = 0;
    setTimeout(() => setPlaying(true), 450);
    if (state.micro && state.micro.neurons.includes(name)) compile();
  } catch (e) {
    toast(e.message, true);
  } finally {
    $("fire-btn").disabled = false;
  }
}

function setPlaying(v) {
  state.playing = v;
  scene.setContinuous(v);
  $("play-icon").innerHTML = v ? '<path d="M7 5h4v14H7zM13 5h4v14h-4z"/>' : '<path d="M7 5l12 7-12 7z"/>';
}

let _P = null;
function frameValues(f) {
  const W = state.walk;
  const n = W.prob.length;
  const i0 = Math.min(n - 1, Math.floor(f)), i1 = Math.min(n - 1, i0 + 1), a = f - i0;
  const r0 = W.prob[i0], r1 = W.prob[i1];
  if (!_P || _P.length !== r0.length) _P = new Float32Array(r0.length);
  const P = _P;
  for (let k = 0; k < P.length; k++) P[k] = r0[k] * (1 - a) + r1[k] * a;
  return { P, t: W.times[i0] * (1 - a) + W.times[i1] * a, part: W.participation[i0] };
}

function renderFrame() {
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
  for (let k = 0; k < P.length; k++) {
    const v = rel ? P[k] / Math.max(max, 1e-12) : Math.sqrt(P[k] / pfire);
    vals[k] = Math.min(1, v);
  }
  scene.setActivity(vals);
  $("time-label").textContent = `t = ${t.toFixed(1)}`;
  // El panel de texto se actualiza ~8 veces por segundo (el DOM es caro; la escena va a 60 fps)
  const now = performance.now();
  if (state.playing && now - (renderFrame._lastUI ?? 0) < 120) return;
  renderFrame._lastUI = now;
  $("timeline").value = Math.round((1000 * state.frame) / (state.walk.prob.length - 1));
  $("m-active").textContent = active;
  $("m-part").textContent = part.toFixed(1);
  $("m-top").textContent = state.neurons[top].name;
  // top 6
  const order = Array.from(P.keys()).sort((a, b) => P[b] - P[a]).slice(0, 6);
  $("toplist").innerHTML = order.map((k) =>
    `<li data-n="${state.neurons[k].name}"><span>${state.neurons[k].name}</span>` +
    `<span class="bar" style="width:${(100 * P[k]) / Math.max(max, 1e-12)}%"></span>` +
    `<span class="p">${(100 * P[k]).toFixed(1)}%</span></li>`).join("");
}

let last = performance.now();
function loop(now) {
  const dt = (now - last) / 1000;
  last = now;
  if (state.playing && state.walk) {
    const fps = 16 * parseFloat($("speed").value);
    state.frame += dt * fps;
    if (state.frame >= state.walk.prob.length - 1) { state.frame = state.walk.prob.length - 1; setPlaying(false); }
    renderFrame();
  }
  requestAnimationFrame(loop);
}

// ------------------------------------------------------------------ microcircuito
function selectedPreset() { return state.presets.find((p) => p.id === state.preset); }

async function compile() {
  const pr = selectedPreset();
  if (!pr) return;
  const src = pr.neurons.includes(state.source) ? state.source : pr.default_source;
  const body = {
    preset: pr.id, sources: [src], theta: parseFloat($("theta").value), gamma: parseFloat($("gamma").value),
    t: parseFloat($("tmicro").value), mode: state.mode, shots: 2000,
  };
  $("compile-btn").disabled = true;
  $("compile-btn").textContent = "Compilando…";
  try {
    const r = await api.simulate(body);
    state.micro = r;
    state.ionqSeries = null;
    renderMicro();
  } catch (e) {
    toast(e.message, true);
  } finally {
    $("compile-btn").disabled = false;
    $("compile-btn").textContent = "Compilar y simular";
  }
}

function renderMicro() {
  const r = state.micro;
  if (!r) return;
  const res = r.resources;
  const F = res.fidelity_estimate;
  const tv = r.circuit_ideal.tvd_vs_exact;
  $("chips").innerHTML = [
    `<span class="chip">qubits <b>${r.n_qubits}</b></span>`,
    `<span class="chip">ZZ <b>${res.zz_gates}</b></span>`,
    `<span class="chip">GPi2 <b>${res.gpi_gates}</b></span>`,
    r.mode === "trotter" ? `<span class="chip">pasos <b>${r.steps}</b></span>` : `<span class="chip">Givens <b>${res.logical_hops}</b></span>`,
    `<span class="chip ${F > 0.75 ? "good" : "warn"}">F<sub>hw</sub> <b>${F.toFixed(2)}</b></span>`,
    `<span class="chip" title="Distancia entre la distribución del circuito ideal y la teoría exacta">TVD vs teoría <b>${tv.toFixed(3)}</b></span>`,
    r.noisy_local_note ? `<span class="chip" title="${r.noisy_local_note}">sin ruido local (&gt;10 qubits)</span>` : "",
    r.noisy_local ? `<span class="chip">aceptados <b>${(100 * r.noisy_local.accepted_fraction).toFixed(0)}%</b></span>` : "",
  ].join("");

  const labels = r.neurons;
  const series = [
    { key: "exact", name: "Teoría exacta", values: r.exact.marginals },
    { key: "ideal", name: "Circuito ideal", values: r.circuit_ideal.marginals },
  ];
  if (r.noisy_local) series.push({ key: "noisy", name: "Ruido Forte (post-sel.)", values: r.noisy_local.marginals_postselected });
  if (state.ionqSeries) series.push({ key: "ionq", name: state.ionqSeries.name, values: state.ionqSeries.values });
  const srcIdx = r.sources.map((s) => labels.indexOf(s));
  groupedBars($("bars"), labels, series, { highlight: srcIdx });
  $("bars-legend").innerHTML = series.map((s) => `<span><i style="background:${SERIES_COLORS[s.key]}"></i>${s.name}</span>`).join("");
  timeSeries($("series"), r.exact_series.times, r.exact_series.marginals, labels, { marker: r.t });
  circuitDiagram($("circuit"), r.circuit.logical);
  $("circ-count").textContent = `· ${r.circuit.logical.gates.length} compuertas lógicas`;

  // resaltar neuronas del microcircuito en el gusano
  scene.setHighlight(labels.map((nm) => state.index.get(nm)));
}

// ------------------------------------------------------------------ IonQ
function ionqHint() {
  const h = state.health;
  if (!h) return;
  const qpu = $("backend").value.startsWith("qpu");
  if (!h.ionq_configured) {
    $("ionq-hint").innerHTML = "Para enviar trabajos, agrega <b>IONQ_API_KEY</b> en <code>backend/.env</code> y reinicia el servidor.";
    $("submit-btn").disabled = true;
  } else if (qpu && !h.allow_qpu) {
    $("ionq-hint").innerHTML = "QPU bloqueada: define <b>ALLOW_QPU=true</b> en <code>backend/.env</code> (tiene costo).";
    $("submit-btn").disabled = true;
  } else {
    $("ionq-hint").textContent = qpu ? "Se enviará al hardware real de IonQ." : "Simulador de IonQ con modelo de ruido de Forte (sin costo de QPU).";
    $("submit-btn").disabled = false;
  }
}

async function submitIonQ() {
  const r = state.micro;
  if (!r) { toast("Primero compila el microcircuito"); return; }
  const body = {
    preset: state.preset, sources: r.sources, theta: r.theta, gamma: r.gamma, t: r.t, mode: r.mode,
    steps: r.steps, order: r.order, shots: parseInt($("shots").value, 10), backend: $("backend").value,
    noise_model: "forte-1", gateset: "native",
  };
  $("submit-btn").disabled = true;
  try {
    const job = await api.submit(body);
    toast(`Trabajo enviado: ${job.job_id.slice(0, 8)}…`);
    await refreshJobs();
    pollJob(job.job_id);
  } catch (e) {
    toast(e.message, true);
  } finally {
    ionqHint();
  }
}

async function pollJob(id) {
  try {
    const rec = await api.job(id);
    if (rec.status === "completed" && rec.analysis) {
      showJob(rec);
      refreshJobs();
      return;
    }
    if (rec.status === "failed" || rec.status === "canceled") { toast(`Trabajo ${rec.status}`, true); refreshJobs(); return; }
  } catch (e) { /* reintentar */ }
  setTimeout(() => pollJob(id), 5000);
}

function showJob(rec) {
  const p = rec.params;
  if (!state.micro || JSON.stringify(state.micro.neurons) !== JSON.stringify(p.neurons)) {
    toast("Ese trabajo usa otro microcircuito; compílalo primero para comparar.");
  }
  state.ionqSeries = {
    name: `IonQ ${rec.backend}${rec.noise_model ? " (" + rec.noise_model + ")" : ""}`,
    values: rec.analysis.marginals_postselected,
  };
  renderMicro();
  toast(`IonQ: TVD post-selección = ${rec.analysis.tvd_postselected.toFixed(3)} · aceptados ${(100 * rec.analysis.accepted_fraction).toFixed(0)}%`);
}

async function refreshJobs() {
  try {
    const { jobs } = await api.jobs();
    $("jobs").innerHTML = jobs.slice(0, 8).map((j) =>
      `<li data-id="${j.job_id}"><span>${j.backend} · t=${j.params?.t ?? "?"}</span>` +
      `<span class="st ${j.status}">${j.status}</span></li>`).join("");
  } catch { /* sin trabajos */ }
}

function exportJSON() {
  const r = state.micro;
  if (!r) { toast("Primero compila el microcircuito"); return; }
  const job = {
    type: "ionq.circuit.v1", name: `cerebro-${state.preset}-t${r.t}`, shots: parseInt($("shots").value, 10),
    backend: $("backend").value, ...( $("backend").value === "simulator" ? { noise: { model: "forte-1" } } : {}),
    input: r.circuit.ionq_native,
  };
  const blob = new Blob([JSON.stringify(job, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `ionq_${state.preset}_t${r.t}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
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
    renderFrame();
  });
  $("relative").addEventListener("change", renderFrame);
  $("show-edges").addEventListener("change", () => scene.setEdgesVisible($("show-edges").checked));
  $("quality").value = savedQuality;
  $("quality").addEventListener("change", () => {
    const q = $("quality").value;
    try { localStorage.setItem("cerebro-calidad", q); } catch { /* sin almacenamiento */ }
    scene.setQuality(q);
  });
  scene.on("quality", (q, auto) => {
    const opt = $("quality").querySelector('option[value="auto"]');
    opt.textContent = `Auto (${QUALITY[q].label.toLowerCase()})`;
    if (auto) toast(`Calidad gráfica ajustada a "${QUALITY[q].label}" para mantener la fluidez`);
  });
  $("autorotate").addEventListener("change", () => scene.setAutoRotate($("autorotate").checked));
  $("toplist").addEventListener("click", (e) => {
    const li = e.target.closest("li");
    if (li) scene.focus(state.index.get(li.dataset.n));
  });
  $("preset").addEventListener("change", () => {
    state.preset = $("preset").value;
    $("preset-desc").textContent = selectedPreset()?.description ?? "";
    compile();
  });
  $("mode-seg").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    state.mode = b.dataset.mode;
    document.querySelectorAll("#mode-seg button").forEach((x) => x.classList.toggle("active", x === b));
    compile();
  });
  $("compile-btn").addEventListener("click", compile);
  $("backend").addEventListener("change", ionqHint);
  $("submit-btn").addEventListener("click", submitIonQ);
  $("export-btn").addEventListener("click", exportJSON);
  $("jobs").addEventListener("click", async (e) => {
    const li = e.target.closest("li");
    if (!li) return;
    try {
      const rec = await api.job(li.dataset.id);
      if (rec.analysis) showJob(rec); else toast(`Estado: ${rec.status}`);
    } catch (err) { toast(err.message, true); }
  });

  scene.on("pick", (i) => fire(state.neurons[i].name));
  const tip = $("tooltip");
  scene.on("hover", (i, px) => {
    if (i < 0 || !px) { tip.classList.remove("show"); return; }
    const d = state.neurons[i];
    let p = "";
    if (state.walk) {
      const { P } = frameValues(state.frame);
      p = `<br>P(disparo) = <b>${(100 * P[i]).toFixed(2)}%</b>`;
    }
    tip.innerHTML = `<b>${d.name}</b> <span class="tag ${d.type}">${TYPE_ES[d.type]}</span><br>${d.degree} conexiones${p}<br><span style="color:#5b6684">clic: disparar láser aquí</span>`;
    tip.style.left = `${px[0] + 14}px`;
    tip.style.top = `${px[1] + 14}px`;
    tip.classList.add("show");
  });
}

// ------------------------------------------------------------------ arranque
async function init() {
  bindUI();
  requestAnimationFrame(loop);
  try {
    state.health = await api.health();
    const pill = $("backend-pill");
    pill.textContent = state.health.ionq_configured ? "IonQ conectado" : "modo local · sin clave IonQ";
    pill.className = `pill ${state.health.ionq_configured ? "ok" : "warn"}`;
    const con = await api.connectome();
    state.neurons = con.neurons;
    con.neurons.forEach((d, i) => state.index.set(d.name, i));
    $("neuron-list").innerHTML = con.neurons.map((d) => `<option value="${d.name}">${TYPE_ES[d.type]}</option>`).join("");
    scene.setData(con.neurons, con.edges);
    const { microcircuits } = await api.microcircuits();
    state.presets = microcircuits;
    $("preset").innerHTML = microcircuits.map((m) =>
      `<option value="${m.id}">${m.name}${m.hardware_ready ? " · listo para hardware" : ""}</option>`).join("");
    $("preset-desc").textContent = selectedPreset()?.description ?? "";
    ionqHint();
    refreshJobs();
    $("loader").classList.add("hide");
    neuronCard(state.source);
    await compile();
    setTimeout(() => fire("AVM"), 700);
  } catch (e) {
    $("loader").querySelector("p").textContent = `No se pudo conectar con el backend (${e.message}). ¿Está corriendo "python run.py"?`;
    $("backend-pill").textContent = "backend desconectado";
    $("backend-pill").className = "pill err";
  }
}

init();
