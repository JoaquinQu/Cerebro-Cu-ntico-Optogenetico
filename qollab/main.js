// Optogenetic Quantum Brain · Qollab page (JS / Qiskit)
//
//  1. Laser → exact quantum walk on the 302 neurons (theory, computed in Python/numpy).
//  2. Quantum cascade → each step is a 10-qubit Qiskit circuit (the neuron that fired and its
//     9 neighbours) run on the selected `backend`; the measured spike triggers the next step.
//  3. Fixed microcircuit → Qiskit circuit (RX + RXX·RYY): theory, ideal and noisy, and ONE job on
//     the backend (built-in simulator, IBM or IonQ noisy simulators, or IonQ Forte hardware).
//
// This effort is supported by Qollab & IonQ.
import { QUALITY, WormScene } from "./js/escena.js";
import { dataTable, groupedBars, SERIES_COLORS, timeSeries } from "./js/graficos.js";
import { py, respirar } from "./js/python.js";

const $ = (id) => document.getElementById(id);
const TYPE_ES = { sensory: "sensory", interneuron: "interneuron", motor: "motor", unknown: "—" };
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

// Estado de la cascada cuántica
const cascade = { running: false, stop: false, armed: false, centers: [], steps: [] };
// Capítulo visible (1 luz · 2 medir · 3 circuito) y narración guardada por capítulo
const ui = { chapter: 1, narr: {}, adj: [] };
const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));

const HELP = {
  theta: "θ is the light dose. The laser is an RX(θ) rotation on the neuron's qubit: θ = π always fires it, " +
    "θ = π/2 fires it half of the time. It scales how bright the response is, not its shape.",
  participation: "How many neurons share the excitation at this moment (the inverse participation ratio). " +
    "1 means it is all on one neuron; 302 would mean spread evenly over the whole worm.",
  tau: "τ is how long the excitation evolves as a wave before we measure it. Each measurement collapses the wave onto " +
    "one neuron. Measure too often (small τ) and the wave never gets to move: that is the quantum Zeno effect.",
  gamma: "γ is the strength of every synapse in the Hamiltonian H = γ Σ J_ij (XX + YY)/2. " +
    "Doubling γ makes everything happen twice as fast.",
  shots: "A shot is one run of the circuit followed by one measurement. Quantum results are random, so the circuit " +
    "is repeated many times and we count how often each neuron came out as 1.",
  trotter: "The evolution e^(−iHt) is not a single gate. Trotter splits it into short steps of two-qubit RXX·RYY gates " +
    "(more steps: more accurate, but more gates and more noise). Givens skips the time steps and prepares the final " +
    "state directly, with fewer gates.",
  postsel: "With one laser, at most one neuron can be excited. Shots with two or more 1s can only come from hardware " +
    "noise, so they are discarded. It is a cheap form of error mitigation.",
  tvd: "Total variation distance: how different two probability distributions are. 0 means identical, " +
    "1 means completely different. Below about 0.05 is a very good match.",
};
const DOS_QUBITS = new Set(["rxx", "ryy", "rzz", "rzx", "cx", "cz", "ecr", "ms", "zz", "swap", "iswap", "xx_plus_yy"]);

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
  if (i == null) { $("neuron-card").textContent = "Neuron not found"; return; }
  const d = state.neurons[i];
  const nt = d.neurotransmitters?.length ? d.neurotransmitters.join(", ") : "—";
  $("neuron-card").innerHTML =
    `<b>${esc(d.name)}</b><span class="tag ${d.type}">${TYPE_ES[d.type]}</span><br>` +
    `${d.degree} connections · neurotransmitter: ${esc(nt)}<br>` +
    `anteroposterior position: ${d.y.toFixed(0)} µm`;
}

// ------------------------------------------------------------------ narración
/** Texto "qué estás viendo" sobre la escena. Se guarda por capítulo y se muestra el del visible. */
function narrate(ch, kicker, html, tone = "") {
  ui.narr[ch] = { kicker, html, tone };
  if (ch === ui.chapter) showNarration();
}
function showNarration() {
  const n = ui.narr[ui.chapter] ?? { kicker: "", html: "" };
  $("narr-kicker").textContent = n.kicker;
  $("narr-text").innerHTML = n.html;
  $("narration").className = `narration ${n.tone}`;
  $("narration").hidden = !n.html;
}

/** Distancias en sinapsis desde una neurona (BFS sobre el conectoma completo). */
function graphDistances(src) {
  const d = new Int16Array(state.neurons.length).fill(-1);
  d[src] = 0;
  const q = [src];
  for (let h = 0; h < q.length; h++) {
    for (const v of ui.adj[q[h]]) if (d[v] < 0) { d[v] = d[q[h]] + 1; q.push(v); }
  }
  return d;
}

/** Busca un ejemplo concreto de interferencia: una neurona lejana más brillante que un vecino directo. */
function interferenceExample(W) {
  const src = state.index.get(W.source);
  const n = state.neurons.length, F = W.prob.length;
  const avg = new Float64Array(n);
  for (const row of W.prob) for (let k = 0; k < n; k++) avg[k] += row[k] / F;
  const d = graphDistances(src);
  let near = -1, far = -1;
  for (let k = 0; k < n; k++) {
    if (d[k] === 1 && (near < 0 || avg[k] < avg[near])) near = k;
    if (d[k] >= 2 && (far < 0 || avg[k] > avg[far])) far = k;
  }
  if (near < 0 || far < 0 || avg[far] <= 1.5 * avg[near]) return null;
  return { near: state.neurons[near].name, far: state.neurons[far].name, hops: d[far],
    ratio: avg[far] / Math.max(avg[near], 1e-9), neighbours: d.filter((v) => v === 1).length };
}

function narrateWalk() {
  const W = state.walk;
  const ex = interferenceExample(W);
  const lead = `<b>${esc(W.source)}</b> is lit. The excitation does not hop around like a ball: it spreads as a ` +
    `<span class="q">wave</span> through every synapse at once, and the paths <b>add up or cancel</b>.`;
  const tail = ex
    ? ` Look at <b>${esc(ex.far)}</b>, ${ex.hops} synapses away: on average it glows ${ex.ratio >= 10 ? "over 10" : ex.ratio.toFixed(0)}× more than ` +
      `<b>${esc(ex.near)}</b>, a direct neighbour. That is interference.`
    : " Bright and dark spots that do not follow distance are interference.";
  narrate(1, "What you're seeing · exact theory", lead + tail);
}

// ------------------------------------------------------------------ capítulos
const TABS = [1, 2, 3].map((n) => $(`tab-${n}`));

function setChapter(n, { focusTab = false } = {}) {
  if (n === ui.chapter && !focusTab) return;
  const prev = ui.chapter;
  ui.chapter = n;
  TABS.forEach((t, i) => {
    const on = i + 1 === n;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    $(`chap-${i + 1}`).hidden = !on;
  });
  if (focusTab) TABS[n - 1].focus();
  closeHelp();
  if (prev !== n) {
    document.querySelector(".side").scrollTop = 0;
    if (prev === 1) setPlaying(false);
    restoreScene();
  }
  showNarration();
}

/** Pone la escena en el estado que corresponde al capítulo visible. */
function restoreScene() {
  const ch = ui.chapter;
  $("mini-circ").hidden = !(ch === 2 && cascade.steps.length);
  if (ch === 1) {
    scene.setHighlight([]);
    scene.setTrail(null);
    if (state.walk && state.walk.source !== state.source) { fire(state.source); return; }
    scene.setLabel(state.index.get(state.source), `⚡ ${state.source}`);
    renderFrame(true);
  } else if (ch === 2) {
    const last = cascade.steps[cascade.steps.length - 1];
    if (last && cascade.centers[0] === state.source) {
      applyCascadeScene(last);
    } else {
      showSourceOnly();
      if (!cascade.running) {
        narrate(2, "Ready to measure", `The cascade starts from <b>${esc(state.source)}</b>. Each step builds a ` +
          `<span class="q">10-qubit circuit</span>, lets the wave spread for a time τ, and then <span class="a">measures</span> it. ` +
          "Press <b>Start cascade</b>.");
      }
    }
  } else {
    applyMicroScene();
  }
}

function showSourceOnly() {
  const vals = new Float32Array(state.neurons.length);
  const i = state.index.get(state.source);
  vals[i] = 1;
  scene.setHighlight([]);
  scene.setTrail(null);
  scene.setActivity(vals);
  scene.setLabel(i, `⚡ ${state.source}`);
}

/** Capítulo 2 o 3: elegir una neurona en el gusano sólo cambia la fuente (no lanza el walk). */
function selectSource(name) {
  stopCascade();
  state.source = name;
  $("neuron-input").value = name;
  neuronCard(name);
  cascadeLabel();
  if (ui.chapter === 2) restoreScene();
  announce(`Source neuron: ${name}.`);
}

// ------------------------------------------------------------------ ayuda "?" y ajustes
function openHelp(btn) {
  const pop = $("help-pop");
  if (!pop.hidden && openHelp._btn === btn) { closeHelp(); return; }
  closeHelp();
  const text = HELP[btn.dataset.help] ?? "";
  $("help-text").textContent = text;
  pop.hidden = false;
  const app = $("app").getBoundingClientRect(), r = btn.getBoundingClientRect();
  const w = pop.offsetWidth;
  pop.style.left = `${Math.max(8, Math.min(app.width - w - 8, r.left - app.left - w / 2 + 8))}px`;
  pop.style.top = `${r.bottom - app.top + 8}px`;
  btn.setAttribute("aria-expanded", "true");
  openHelp._btn = btn;
  announce(text);
}
function closeHelp({ refocus = false } = {}) {
  const pop = $("help-pop");
  if (pop.hidden) return;
  pop.hidden = true;
  const b = openHelp._btn;
  openHelp._btn = null;
  if (b) { b.setAttribute("aria-expanded", "false"); if (refocus) b.focus(); }
}

function setLab(open) {
  $("lab").hidden = !open;
  $("lab-btn").setAttribute("aria-expanded", String(open));
  if (open) {
    document.querySelector(".side").scrollTop = 0;
    $("lab-close").focus();
  } else {
    $("lab-btn").focus();
  }
}

// ------------------------------------------------------------------ 1 · láser
async function fire(name = $("neuron-input").value.trim().toUpperCase()) {
  if (!state.index.has(name)) { toast(`There is no neuron "${name}"`, true); return; }
  stopCascade();
  state.source = name;
  cascadeLabel();
  $("neuron-input").value = name;
  neuronCard(name);
  const idx = state.index.get(name);
  const p = params();
  const visible = ui.chapter === 1; // en otros capítulos se recalcula sin tocar la escena
  $("fire-btn").disabled = true;
  if (visible) {
    scene.setTrail(null);
    scene.setHighlight([]);
    scene.setLabel(idx, `⚡ ${name}`);
    scene.fireLaser(idx, Math.sin(p.theta / 2) ** 2);
    narrate(1, "Laser on", `Firing the laser at <b>${esc(name)}</b>…`);
  }
  await respirar();
  try {
    state.walk = await py.walk({ fuente: name, theta: p.theta, gamma: p.gamma, t_max: p.t_max, cuadros: 160 });
    state.frame = 0;
    describeWalk();
    narrateWalk();
    if (!visible) {
      state.frame = state.walk.prob.length - 1;
    } else if (REDUCED) {
      // Sin animación automática: se muestra un instante intermedio y se reproduce a pedido.
      state.frame = Math.round((state.walk.prob.length - 1) * 0.3);
      renderFrame(true);
    } else {
      setTimeout(() => { if (ui.chapter === 1) setPlaying(true); }, 450);
    }
    const pr = selectedPreset();
    if (pr && pr.neuronas.includes(name) && state.micro && state.micro.fuente !== name) compile();
  } catch (e) {
    toast(`Python error: ${e.message}`, true);
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
  const msg = `Laser on ${W.source}, fire probability ${pct(W.fire_probability)}. ` +
    `At the end of the simulation the most likely neurons are: ${top}.`;
  $("scene").setAttribute("aria-label", `3D C. elegans worm. ${msg}`);
  announce(msg);
}

function setPlaying(v) {
  if (v && ui.chapter !== 1) v = false;
  state.playing = v;
  scene.setContinuous(v);
  $("play-btn").setAttribute("aria-pressed", String(v));
  $("play-btn").setAttribute("aria-label", v ? "Pause" : "Play");
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
  const pfire = state.walk.fire_probability;
  let max = 0, top = 0, active = 0;
  for (let k = 0; k < P.length; k++) {
    if (P[k] > max) { max = P[k]; top = k; }
    if (P[k] > 0.005) active++;
  }
  // No dividir por sin²(θ/2): es el único efecto de θ con un láser y la escena lo borraría.
  const rel = $("relative").checked;
  const vals = (renderFrame._vals ??= new Float32Array(P.length));
  for (let k = 0; k < P.length; k++) vals[k] = Math.min(1, rel ? (pfire * P[k]) / Math.max(max, 1e-12) : Math.sqrt(P[k]));
  if (ui.chapter === 1) scene.setActivity(vals);
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
    return `<li><button type="button" data-n="${nm}" aria-label="${nm}: ${pct(P[k])}. Center the view on ${nm}">` +
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
  announce(`t = ${t.toFixed(1)}; most likely ${state.neurons[top].name} with ${pct(P[top])}`);
}


// ------------------------------------------------------------------ 2 · cascada cuántica
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
// Pasos de Trotter por ventana: con τ ≤ 4.5 basta 1 (TVD ≈ 0.02); con τ = 8 hacen falta 2.
const trotterReps = (tau) => Math.max(1, Math.ceil(tau / 4.5));
const dosQubits = (ops) => Object.entries(ops || {}).reduce((a, [k, v]) => a + (DOS_QUBITS.has(k.toLowerCase()) ? v : 0), 0);

function cascadeLabel() {
  if (!cascade.running) $("casc-btn").textContent = `Start cascade from ${state.source}`;
}

function stopCascade() {
  if (cascade.running) cascade.stop = true;
}

async function runCascade() {
  if (cascade.running) return;
  if (!BACKEND || !state.backend) { toast("No backend: press Run on Qollab and pick one.", true); return; }
  const ionq = state.backend.ionq;
  if (ionq && state.jobsSent >= 1) {
    toast("IonQ accepts one job per run: press Stop and then Run to send another one.", true);
    return;
  }
  if (state.backend.hardware && !cascade.armed) {
    cascade.armed = true;
    $("casc-btn").textContent = "Confirm: 1 step on hardware (uses credits)";
    announce("Press the button again to confirm sending to hardware.");
    return;
  }
  cascade.armed = false;
  const total = ionq ? 1 : clamp(parseInt($("casc-pasos").value, 10) || 20, 1, 60);
  const shots = clamp(parseInt($("casc-shots").value, 10) || 200, 20, 2000);
  const tau = parseFloat($("tau").value);
  const { theta, gamma } = params();
  setPlaying(false);
  closeHelp();
  Object.assign(cascade, { running: true, stop: false, centers: [state.source], steps: [] });
  $("casc-btn").disabled = true;
  $("casc-stop").disabled = false;
  $("casc-fig-btn").disabled = true;
  $("casc-log").innerHTML = "";
  let centro = state.source;
  const idx0 = state.index.get(centro);
  showSourceOnly();
  scene.fireLaser(idx0, Math.sin(theta / 2) ** 2);
  narrate(2, "Step 1 · laser", `The laser excites <b>${esc(centro)}</b> with RX(θ). Sending its 10-qubit circuit to ` +
    `<b>${esc(state.backend.nombre)}</b>…`);
  if (ionq) toast("IonQ accepts one job per run: only the first step will run.");
  let fin = "completa";
  try {
    for (let k = 1; k <= total; k++) {
      if (cascade.stop) { fin = "detenida"; break; }
      $("casc-estado").textContent = `Step ${k} of ${total}: 10-qubit circuit on ${state.backend.nombre}…`;
      await respirar();
      const params = { centro, theta: k === 1 ? theta : Math.PI, tau, gamma, pasos_trotter: trotterReps(tau) };
      const r = await py.paso(BACKEND, { ...params, shots });
      r.params = params;
      r.k = k;
      r.shots = shots;
      state.jobsSent++;
      cascade.steps.push(r);
      const salto = !!(r.spike && r.spike !== centro);
      r.salto = salto;
      if (salto) cascade.centers.push(r.spike);
      renderCascadePanel(r, k, total);
      if (ui.chapter === 2 && !REDUCED) {
        narrateSuperposition(r);
        await scene.collapse(r.ventana_indices, r.teoria_ventana, r.spike_indice);
      }
      if (ui.chapter === 2) applyCascadeScene(r);
      narrateMeasurement(r);
      if (!r.spike) {
        fin = r.motivo_fin === "vacio" ? "vacio" : "perdida";
        break;
      }
      centro = r.spike;
      if (!REDUCED) await sleep(salto ? 600 : 250);
    }
  } catch (e) {
    fin = "error";
    toast(`The step failed: ${e.message}`, true);
  } finally {
    cascade.running = false;
    $("casc-stop").disabled = true;
    $("casc-fig-btn").disabled = cascade.steps.length === 0;
    const bloqueado = state.backend.ionq && state.jobsSent >= 1;
    $("casc-btn").disabled = bloqueado;
    cascadeLabel();
    if (bloqueado) $("run-btn").disabled = true;
    const n = cascade.steps.length, saltos = cascade.centers.length - 1;
    const motivo = { completa: "", detenida: " (stopped)", error: " (error)",
      vacio: ": the neuron did not fire (shot with no excitation)", perdida: ": no valid shot left" }[fin];
    const msg = `Cascade${motivo}. ${n} circuits run, ${saltos} jumps: ${cascade.centers.join(" → ")}.`;
    if (n) {
      narrate(2, "Cascade finished", `<b>${n}</b> circuits, <b>${saltos}</b> jumps: ` +
        `<span class="a">${cascade.centers.map(esc).join(" → ")}</span>. ` +
        (saltos <= 1 && tau <= 4
          ? "With such a short τ, measuring keeps pinning the spike in place: the quantum Zeno effect. Try τ = 8."
          : "Each jump was decided by one measurement. Open <b>What changes when you measure?</b> to compare with the unmeasured wave."),
      "collapse");
    }
    $("casc-estado").textContent = msg + (bloqueado ? " For another job on IonQ, press Stop and Run." : "");
    announce(msg);
  }
}

/** Escena tras la medida: la neurona medida brilla; el resto de la ventana queda tenue y con anillo. */
function applyCascadeScene(r) {
  const N = state.neurons.length;
  const vals = new Float32Array(N);
  const max = Math.max(...r.medida, 1e-9);
  r.ventana_indices.forEach((g, i) => { vals[g] = 0.05 + 0.3 * (r.medida[i] / max); });
  if (r.spike_indice != null) vals[r.spike_indice] = 1;
  scene.setActivity(vals);
  scene.setHighlight(r.ventana_indices);
  scene.setTrail(cascade.centers.map((nm) => state.index.get(nm)));
  const lab = r.spike_indice ?? r.ventana_indices[0];
  scene.setLabel(lab, r.spike ? `⚡ ${r.spike}` : `∅ ${r.centro}`);
}

/** Probabilidades de la ventana normalizadas entre neuronas (sin el vacío). */
function windowProbs(values) {
  const s = values.reduce((a, b) => a + b, 0) || 1;
  return values.map((v) => v / s);
}

function narrateSuperposition(r) {
  const p = windowProbs(r.teoria_ventana);
  const top = p.map((v, i) => [v, i]).sort((a, b) => b[0] - a[0]).slice(0, 3)
    .map(([v, i]) => `${esc(r.ventana[i])} ${pct(v)}`).join(", ");
  narrate(2, `Step ${r.k} · superposition`, `Before measuring, the excitation is in <span class="q">all 10 neurons at once</span> ` +
    `(${top}…). The measurement will pick one.`);
}

function narrateMeasurement(r) {
  const i = r.spike ? r.ventana.indexOf(r.spike) : -1;
  const share = i >= 0 ? pct(r.medida[i] / Math.max(1e-9, r.medida.reduce((a, b) => a + b, 0))) : "";
  let html;
  if (!r.spike) {
    html = r.motivo_fin === "vacio"
      ? `Measured: <b>no neuron fired</b>. The light did not excite ${esc(r.centro)} in this shot ` +
        "(that happens with probability cos²(θ/2)). The cascade stops."
      : "Measured: no valid shot was left after post-selection. The cascade stops.";
  } else if (r.salto) {
    html = `Measured! The wave <span class="a">collapsed onto ${esc(r.spike)}</span>, which came out as 1 in ${share} of the shots. ` +
      `${esc(r.spike)} fires and starts step ${r.k + 1}.`;
  } else {
    html = `It collapsed back onto <b>${esc(r.spike)}</b> itself (${share} of the shots). ` +
      ((r.params?.tau ?? 8) <= 4
        ? "With a short τ this is likely: measuring often freezes the walk (Zeno effect)."
        : "The wave had not fully left yet, so staying put was the most likely outcome. It tries again.");
  }
  narrate(2, `Step ${r.k} · measured`, html, "collapse");
}

function renderCascadePanel(r, k, total) {
  const salto = r.salto;
  const twoq = dosQubits(r.ops_transpilado) || dosQubits(r.ops_escritas);
  $("casc-chips").innerHTML = [
    `<span class="chip">step <b>${k}/${total}</b></span>`,
    `<span class="chip">qubits <b>${r.ventana.length}</b></span>`,
    twoq ? `<span class="chip" title="Two-qubit gates after transpiling for the backend">2q <b>${twoq}</b></span>` : "",
    `<span class="chip" title="Shots with at most one excitation (post-selection)">valid <b>${pct(r.fraccion_valida)}</b></span>`,
    r.fraccion_vacio > 0 ? `<span class="chip warn" title="Shots with no excitation: the neuron did not fire (cos²(θ/2) on the first step)">empty <b>${pct(r.fraccion_vacio)}</b></span>` : "",
    `<span class="chip warn" title="How much would leak out of the window on the full network at this τ">leak <b>${pct(r.fuga_red)}</b></span>`,
    `<span class="chip ${salto ? "good" : ""}">spike <b>${esc(r.spike ?? "—")}</b></span>`,
  ].join("");
  const series = [
    { key: "exact", name: "Theory in the window", values: r.teoria_ventana },
    { key: "backend", name: `Measured (${r.backend})`, values: r.medida },
  ];
  groupedBars($("casc-bars"), r.ventana, series, { highlight: [0] });
  $("casc-legend").innerHTML = series.map((s) => `<span><i style="background:${SERIES_COLORS[s.key]}"></i>${esc(s.name)}</span>`).join("");
  dataTable($("casc-table"), r.ventana, series, `Window centred on ${r.centro}, step ${k}`);
  drawMiniCircuit(r);
  const li = document.createElement("li");
  li.innerHTML = salto
    ? `<b>${esc(r.centro)}</b> <span class="salto">→ ${esc(r.spike)}</span> · valid ${pct(r.fraccion_valida)}`
    : r.spike
      ? `<b>${esc(r.centro)}</b> stays (the spike came out on the centre)`
      : `<b>${esc(r.centro)}</b> · no spike`;
  $("casc-log").appendChild(li);
  $("casc-log").scrollTop = $("casc-log").scrollHeight; // sin mover el panel entero
  if (salto) announce(`Step ${k}: ${r.spike} fires.`);
}

/** Circuito del paso dibujado al instante en SVG (sin matplotlib): RX → e^{−iτH} → medidas → bits. */
function drawMiniCircuit(r) {
  const names = r.ventana, n = names.length;
  const hot = r.spike ? names.indexOf(r.spike) : -1;
  const dy = 16, y0 = 12, H = y0 + dy * (n - 1) + 14, W = 280;
  const x = { wire0: 46, rx: 54, u0: 96, u1: 162, m: 176, bit: 214, end: 204 };
  const gate1 = r.k === 1 ? "RX(θ)" : "X";
  const reps = r.params?.pasos_trotter ?? 1;
  let g = "";
  names.forEach((nm, i) => {
    const y = y0 + i * dy, h = i === hot ? " hot" : "";
    g += `<text x="${x.wire0 - 4}" y="${y + 3}" text-anchor="end" class="${h.trim()}">${esc(nm)}</text>`;
    g += `<line class="w${h}" x1="${x.wire0}" y1="${y}" x2="${x.end}" y2="${y}"/>`;
    g += `<rect class="meter${h}" x="${x.m}" y="${y - 6}" width="18" height="12" rx="2"/>` +
      `<path d="M${x.m + 3} ${y + 3} Q${x.m + 9} ${y - 5} ${x.m + 15} ${y + 3}" fill="none" stroke="currentColor" class="w${h}"/>`;
    const bit = i === hot ? "1" : "0";
    g += `<text x="${x.bit}" y="${y + 3}" class="${h.trim()}">${bit}${i === hot ? " ← fires" : ""}</text>`;
  });
  g += `<rect class="gate" x="${x.rx}" y="${y0 - 7}" width="34" height="14" rx="3"/>` +
    `<text class="gate-t" x="${x.rx + 17}" y="${y0 + 3}" text-anchor="middle">${gate1}</text>`;
  g += `<rect class="gate-u" x="${x.u0}" y="${y0 - 8}" width="${x.u1 - x.u0}" height="${H - y0 - 4}" rx="5"/>` +
    `<text class="gate-t big" x="${(x.u0 + x.u1) / 2}" y="${H / 2 - 4}" text-anchor="middle">e<tspan dy="-6" font-size="9">−iτH</tspan></text>` +
    `<text x="${(x.u0 + x.u1) / 2}" y="${H / 2 + 12}" text-anchor="middle">τ = ${r.params?.tau ?? ""}</text>` +
    `<text x="${(x.u0 + x.u1) / 2}" y="${H / 2 + 23}" text-anchor="middle">${reps} Trotter</text>`;
  const desc = `Circuit of step ${r.k}: ${n} qubits (${names.join(", ")}). ${gate1} on ${names[0]}, then the XY evolution ` +
    `e^(−iτH) with ${reps} Trotter step${reps > 1 ? "s" : ""}, then all qubits are measured. ` +
    (hot >= 0 ? `Chosen shot: ${names[hot]} = 1, all others 0.` : "Chosen shot: all 0, no neuron fired.");
  $("mini-circ-svg").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(desc)}">${g}</svg>`;
  $("mini-circ-cap").textContent = `· step ${r.k} · ${r.shots ?? ""} shots`;
  $("mini-circ").hidden = ui.chapter !== 2;
}

const CMP = [
  { key: "coherente", name: "Coherent (unmeasured)", color: "#38e1ff" },
  { key: "medido", name: "Measured every τ (full network)", color: "#ffb347" },
  { key: "ventanas", name: "10-qubit cascade", color: "#a78bfa" },
  { key: "clasico", name: "Classical walk", color: "#9aa4bf" },
];

async function runComparison() {
  const btn = $("cmp-btn");
  btn.disabled = true;
  btn.textContent = "Computing…";
  await respirar();
  try {
    const tau = parseFloat($("tau").value);
    const c = await py.comparacion({ centro: state.source, tau, pasos: Math.ceil(48 / tau), gamma: params().gamma });
    const rows = (m) => c.tiempos.map((_, i) => CMP.map((s) => c.curvas[s.key][m][i]));
    const colors = CMP.map((s) => s.color), labels = CMP.map((s) => s.name);
    const dmax = Math.max(1, ...CMP.flatMap((s) => c.curvas[s.key].distancia));
    timeSeries($("cmp-dist"), c.tiempos, rows("distancia"), labels, { colors, ymax: Math.ceil(dmax * 2) / 2,
      ariaLabel: "Mean distance from the origin in synapses over time, for the four dynamics" });
    timeSeries($("cmp-orig"), c.tiempos, rows("origen"), labels, { colors,
      ariaLabel: "Probability of still being on the origin neuron over time, for the four dynamics" });
    $("cmp-legend").innerHTML = CMP.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join("");
    const filas = c.tiempos.map((t) => `t = ${t}`);
    dataTable($("cmp-table"), filas, CMP.map((s) => ({ key: s.key, name: `${s.name}: distance`, values: c.curvas[s.key].distancia })),
      `Mean distance from ${state.source} with τ = ${tau}`);
    $("cmp-table").querySelector("th").textContent = "Time";
    announce(`Comparison ready for τ = ${tau}.`);
  } catch (e) {
    toast(`Python error: ${e.message}`, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Compute comparison";
  }
}

// ------------------------------------------------------------------ 3 · microcircuito
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
  const turno = (compile._turno = (compile._turno ?? 0) + 1); // sólo vale la última petición
  btn.disabled = true;
  btn.textContent = "Computing in Python…";
  await respirar();
  try {
    const r = await py.simular(body);
    if (turno !== compile._turno) return; // llegó una petición más nueva: se descarta esta
    state.micro = r;
    if (state.medido && state.medido.clave !== claveMicro(r)) state.medido = null;
    renderMicro();
    announce(`${r.n_qubits}-qubit microcircuit ready: ${r.recursos.compuertas_2q} two-qubit gates, ` +
      `distance to theory ${r.tvd_circuito.toFixed(3)}.`);
  } catch (e) {
    toast(`Python error: ${e.message}`, true);
  } finally {
    if (turno === compile._turno) {
      btn.disabled = false;
      btn.textContent = "Simulate locally (theory · circuit · noise)";
    }
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
    `<span class="chip" title="Each RXX·RYY hop compiles to ZZ gates on IonQ Forte">2q <b>${res.compuertas_2q}</b></span>`,
    r.modo === "trotter" ? `<span class="chip">steps <b>${r.pasos}</b></span>` : `<span class="chip">Givens <b>${r.saltos.length}</b></span>`,
    `<span class="chip ${F > 0.75 ? "good" : "warn"}" title="Estimated fidelity on IonQ Forte">F<sub>Forte</sub> <b>${F.toFixed(2)}</b></span>`,
    `<span class="chip" title="Total variation distance between the ideal circuit and the exact theory">circuit TVD <b>${r.tvd_circuito.toFixed(3)}</b></span>`,
    r.ruido ? `<span class="chip" title="Fraction of shots that respect the symmetry (≤ 1 excitation)">accepted <b>${pct(r.ruido.fraccion_aceptada)}</b></span>` : "",
    fila ? `<span class="chip good" title="Backend TVD after post-selection">backend TVD <b>${fila.tvd_postseleccion.toFixed(3)}</b></span>` : "",
  ].join("");

  const labels = r.neuronas;
  const series = [
    { key: "exact", name: "Exact theory", values: r.exacta },
    { key: "ideal", name: "Ideal circuit", values: r.ideal },
  ];
  if (r.ruido) series.push({ key: "noisy", name: "Forte-like noise (post-sel.)", values: r.ruido.marginales_postseleccion });
  if (fila) series.push({ key: "backend", name: `${m.backend} (post-sel.)`, values: fila.marginales_postseleccion });
  const ymax = 1.1 * Math.max(r.escala_y ?? 0, 0.05, ...series.flatMap((s) => s.values));
  groupedBars($("bars"), labels, series, { highlight: [labels.indexOf(r.fuente)], max: ymax });
  $("bars-legend").innerHTML = series.map((s) => `<span><i style="background:${SERIES_COLORS[s.key]}"></i>${esc(s.name)}</span>`).join("");
  dataTable($("bars-table"), labels, series, `Fire probability per neuron at t = ${r.t}`);
  const puntos = m ? m.resultados.map((f) => ({ t: f.t, values: f.marginales_postseleccion })) : null;
  timeSeries($("series"), r.serie.tiempos, r.serie.marginales, labels, { marker: r.t, points: puntos });
  if (r.qiskit_texto) {
    $("qiskit-text").textContent = r.qiskit_texto;
    const ops = Object.entries(r.qiskit_ops || {}).map(([k, v]) => `${k}:${v}`).join(" ");
    $("circ-count").textContent = `· ${ops}`;
  } else {
    $("qiskit-text").textContent = "Qiskit is not available in this environment.";
  }
  if (ui.chapter === 3) applyMicroScene();
  narrateMicro();
}

/** Capítulo 3: las neuronas del microcircuito brillan según la teoría exacta a tiempo t. */
function applyMicroScene() {
  const r = state.micro;
  if (!r) { scene.setHighlight([]); scene.setTrail(null); return; }
  const vals = new Float32Array(state.neurons.length);
  const max = Math.max(...r.exacta, 1e-9);
  const idx = r.neuronas.map((nm) => state.index.get(nm));
  idx.forEach((g, i) => { if (g != null) vals[g] = 0.12 + 0.88 * (r.exacta[i] / max); });
  scene.setTrail(null);
  scene.setActivity(vals);
  scene.setHighlight(idx.filter((i) => i != null));
  scene.setLabel(state.index.get(r.fuente), `⚡ ${r.fuente}`);
}

function narrateMicro() {
  const r = state.micro;
  if (!r) return;
  const m = state.medido;
  const fila = m ? m.resultados[m.resultados.length - 1] : null;
  const how = r.modo === "trotter" ? `${r.pasos} Trotter steps` : `${r.saltos.length} Givens rotations`;
  let html = `<b>${r.n_qubits} qubits</b>, one per neuron of this reflex circuit (ringed on the worm). ` +
    `The laser on <b>${esc(r.fuente)}</b> is followed by ${how}: <b>${r.recursos.compuertas_2q}</b> two-qubit gates. ` +
    `The ideal circuit matches exact theory with TVD <b>${r.tvd_circuito.toFixed(3)}</b> (0 = identical).`;
  if (fila) {
    html += ` On <span class="a">${esc(m.backend)}</span> it measured TVD <b>${fila.tvd_postseleccion.toFixed(3)}</b> after discarding ` +
      `${pct(1 - fila.fraccion_aceptada)} of noisy shots.`;
  } else if (r.ruido) {
    html += ` With IonQ-like noise, ${pct(1 - r.ruido.fraccion_aceptada)} of shots break the symmetry and are discarded.`;
  }
  narrate(3, fila ? "Measured on the backend" : "What you're seeing · the circuit", html, fila ? "collapse" : "");
}

// ------------------------------------------------------------------ 3 · backend
function renderBackendInfo() {
  const b = state.backend;
  const pill = $("backend-pill");
  if (!b) {
    pill.textContent = "no backend";
    pill.className = "pill err";
    $("run-hint").textContent = "No backend: press Run on Qollab and pick one.";
    $("run-btn").disabled = true;
    $("casc-btn").disabled = true;
    return;
  }
  pill.textContent = `backend: ${b.nombre}`;
  pill.className = `pill ${b.hardware ? "warn" : "ok"}`;
  $("run-hint").innerHTML = b.hardware
    ? `<b>${esc(b.nombre)}</b> is real IonQ hardware: the job uses credits. Try it first on the Forte remote simulator (free).`
    : b.ionq
      ? `<b>${esc(b.nombre)}</b>: IonQ remote simulator with its noise model (free). IonQ accepts <b>one job</b> per run.`
      : `<b>${esc(b.nombre)}</b>: local simulator (free, no job limit).`;
}

async function runOnBackend() {
  if (!BACKEND || !state.backend) { toast("No backend: press Run on Qollab and pick one.", true); return; }
  if (state.backend.ionq && state.jobsSent >= 1) {
    toast("IonQ accepts one job per run: press Stop and then Run to send another one.", true);
    return;
  }
  if (state.backend.hardware && !state.armedHardware) {
    state.armedHardware = true;
    $("run-btn").textContent = "Confirm: send to hardware (uses credits)";
    announce("Press the button again to confirm sending to hardware.");
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
  btn.textContent = `Running ${tiempos.length} circuit${tiempos.length > 1 ? "s" : ""} in one job…`;
  $("run-result").innerHTML = `<p class="result">Waiting for results from <b>${esc(state.backend.nombre)}</b>…</p>`;
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
    announce(`Results from ${m.backend}: distance to theory ${f.tvd_postseleccion.toFixed(3)} after post-selection, ` +
      `${pct(f.fraccion_aceptada)} of shots accepted.`);
  } catch (e) {
    $("run-result").innerHTML = `<p class="result">The job failed: ${esc(e.message)}</p>`;
    toast(`The job failed: ${e.message}`, true);
  } finally {
    state.armedHardware = false;
    btn.textContent = "Run circuit";
    btn.disabled = state.backend.ionq && state.jobsSent >= 1;
    if (btn.disabled) {
      $("casc-btn").disabled = true; // IonQ: un job por ejecución, también para la cascada
      $("run-hint").innerHTML += " <b>Job sent.</b> For another one, press Stop and Run.";
    }
  }
}

function renderRunResult(m) {
  const ops = (o) => Object.entries(o || {}).map(([k, v]) => `${k}:${v}`).join(" ") || "—";
  $("run-result").innerHTML =
    `<div class="result"><p><b>${esc(m.backend)}</b> · ${m.shots} shots per circuit · ${m.modo}` +
    (m.modo === "trotter" ? ` · ${m.pasos} steps` : "") + (m.job_id ? `<br>job <code>${esc(m.job_id)}</code>` : "") + `</p>` +
    `<div class="data-box"><table><caption class="sr-only">Comparison with theory per time</caption>` +
    `<thead><tr><th scope="col">t</th><th scope="col">raw TVD</th><th scope="col">post-sel. TVD</th><th scope="col">accepted</th></tr></thead><tbody>` +
    m.resultados.map((f) => `<tr><th scope="row">${f.t}</th><td>${f.tvd_bruto.toFixed(3)}</td>` +
      `<td>${f.tvd_postseleccion.toFixed(3)}</td><td>${pct(f.fraccion_aceptada)}</td></tr>`).join("") +
    `</tbody></table></div>` +
    `<p class="hint">Gates as written: <code>${esc(ops(m.ops_escritas))}</code><br>` +
    `After transpiling for the backend: <code>${esc(ops(m.ops_transpilado))}</code></p></div>`;
}

// ------------------------------------------------------------------ figuras de Qiskit (mpl)
const fig = { tipo: null, cache: new Map(), turno: 0 };

function abrirFiguras(tipo) {
  fig.tipo = tipo;
  const esPaso = tipo === "paso";
  $("fig-controls").hidden = !esPaso;
  if (esPaso) {
    $("fig-step").innerHTML = cascade.steps.map((r, i) =>
      `<option value="${i}">${i + 1} · ${esc(r.centro)}${r.spike && r.spike !== r.centro ? ` → ${esc(r.spike)}` : ""}</option>`).join("");
    $("fig-step").value = String(cascade.steps.length - 1);
  }
  $("fig-dialog").showModal();
  dibujarFiguras();
}

function paramsFiguras() {
  if (fig.tipo === "paso") {
    const r = cascade.steps[parseInt($("fig-step").value, 10)];
    const vista = document.querySelector('input[name="fig-vista"]:checked').value;
    return { tipo: "paso", ...r.params, vista, conteos: r.conteos };
  }
  const r = state.micro;
  const fila = state.medido ? state.medido.resultados[state.medido.resultados.length - 1] : null;
  return { tipo: "micro", preset: state.preset, fuente: r.fuente, theta: r.theta, gamma: r.gamma, t: r.t,
    modo: r.modo, pasos: r.pasos, orden: r.orden, conteos: fila?.conteos ?? null };
}

async function dibujarFiguras() {
  const p = paramsFiguras();
  const clave = JSON.stringify(p);
  const turno = ++fig.turno;
  $("fig-estado").textContent = p.vista === "expandida"
    ? "Drawing with Qiskit… the expanded view has hundreds of gates and takes a few seconds."
    : `Drawing with Qiskit…${fig.cache.size ? "" : " The first figure takes about 30 s while matplotlib loads."}`;
  await respirar();
  try {
    let f = fig.cache.get(clave);
    if (!f) { f = await py.figuras(p); fig.cache.set(clave, f); }
    if (turno !== fig.turno) return;
    const ops = Object.entries(f.ops).map(([k, v]) => `${k}: ${v}`).join(", ");
    const medido = f.histograma_tipo === "medido";
    $("fig-title").textContent = f.titulo;
    $("fig-circ").src = f.circuito_svg;
    $("fig-circ").alt = `${f.neuronas.length}-qubit Qiskit circuit (${f.neuronas.join(", ")}). ` +
      `Gates: ${ops}. Depth ${f.profundidad}.`;
    $("fig-circ-cap").textContent = `QuantumCircuit.draw("mpl") · ${ops} · depth ${f.profundidad}`;
    $("fig-hist").src = f.histograma_svg;
    $("fig-hist").alt = medido
      ? "Histogram of the counts measured on the backend, grouped by the neuron that fired."
      : "Ideal distribution of the circuit from the Qiskit Statevector, grouped by excited neuron.";
    $("fig-hist-cap").textContent = medido
      ? "plot_histogram of the counts returned by the backend · ∅ = no neuron fired."
      : "plot_distribution of the ideal Statevector · not run on a backend yet.";
    $("fig-estado").textContent = "";
  } catch (e) {
    if (turno === fig.turno) $("fig-estado").textContent = `Could not draw: ${e.message}`;
  }
}

// ------------------------------------------------------------------ eventos
async function recalcular(conMicro) {
  if (!state.walk || cascade.running) return;
  await fire(state.source);
  if (conMicro) compile();
}

function bindUI() {
  $("fire-btn").addEventListener("click", () => fire());
  $("neuron-input").addEventListener("change", () => neuronCard($("neuron-input").value.trim().toUpperCase()));
  $("neuron-input").addEventListener("keydown", (e) => { if (e.key === "Enter") fire(); });
  $("theta").addEventListener("input", () => {
    const th = parseFloat($("theta").value);
    $("theta-val").textContent = fmtTheta(th);
    $("pfire").textContent = (Math.sin(th / 2) ** 2).toFixed(2);
    $("theta").setAttribute("aria-valuetext", `θ = ${fmtTheta(th)}, fire probability ${(Math.sin(th / 2) ** 2).toFixed(2)}`);
  });
  $("gamma").addEventListener("input", () => { $("gamma-val").textContent = parseFloat($("gamma").value).toFixed(1); });
  $("tmax").addEventListener("input", () => { $("tmax-val").textContent = $("tmax").value; });
  $("theta").addEventListener("change", () => recalcular(true));
  $("gamma").addEventListener("change", () => recalcular(true));
  $("tmax").addEventListener("change", () => recalcular(false));
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
    if (auto) toast(`Graphics quality set to "${QUALITY[q].label}" to keep it smooth`);
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
  $("casc-btn").addEventListener("click", runCascade);
  $("casc-stop").addEventListener("click", stopCascade);
  $("cmp-btn").addEventListener("click", runComparison);
  $("casc-fig-btn").addEventListener("click", () => abrirFiguras("paso"));
  $("micro-fig-btn").addEventListener("click", () => { if (state.micro) abrirFiguras("micro"); });
  $("fig-close").addEventListener("click", () => $("fig-dialog").close());
  $("fig-step").addEventListener("change", dibujarFiguras);
  document.querySelectorAll('input[name="fig-vista"]').forEach((r) => r.addEventListener("change", dibujarFiguras));
  $("tau").addEventListener("input", () => {
    $("tau-val").textContent = $("tau").value;
    $("tau").setAttribute("aria-valuetext", `τ = ${$("tau").value}`);
  });

  // capítulos (pestañas con flechas, Inicio y Fin)
  TABS.forEach((t, i) => {
    t.addEventListener("click", () => setChapter(i + 1));
    t.addEventListener("keydown", (e) => {
      const n = { ArrowRight: i + 2, ArrowLeft: i, Home: 1, End: 3 }[e.key];
      if (n === undefined) return;
      e.preventDefault();
      setChapter(((n - 1 + 3) % 3) + 1, { focusTab: true });
    });
  });
  document.querySelectorAll("[data-goto]").forEach((b) => b.addEventListener("click", () => {
    setChapter(parseInt(b.dataset.goto, 10), { focusTab: true });
  }));
  // ayuda
  document.querySelectorAll("button.help").forEach((b) => {
    b.setAttribute("aria-expanded", "false");
    b.setAttribute("aria-controls", "help-pop");
    b.addEventListener("click", (e) => { e.stopPropagation(); openHelp(b); });
  });
  document.addEventListener("click", (e) => { if (!e.target.closest("#help-pop")) closeHelp(); });
  document.querySelector(".side").addEventListener("scroll", () => closeHelp(), { passive: true });
  // ajustes de laboratorio
  $("lab-btn").addEventListener("click", () => setLab($("lab").hidden));
  $("lab-close").addEventListener("click", () => setLab(false));
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("help-pop").hidden) { closeHelp({ refocus: true }); e.preventDefault(); return; }
    if (!$("lab").hidden && $("lab").contains(document.activeElement)) { setLab(false); e.preventDefault(); }
  });

  scene.on("key", (e) => {
    if (e.key === " " || e.key === "k") { $("play-btn").click(); return true; }
    if (e.key === "ArrowRight") { stepFrames(e.shiftKey ? 16 : 4); return true; }
    if (e.key === "ArrowLeft") { stepFrames(e.shiftKey ? -16 : -4); return true; }
    return false;
  });
  scene.on("pick", (i) => {
    const name = state.neurons[i].name;
    if (ui.chapter === 1) { fire(name); return; }
    if (ui.chapter === 2) { if (!cascade.running) selectSource(name); return; }
    const pr = selectedPreset();
    if (pr && pr.neuronas.includes(name)) { state.source = name; neuronCard(name); cascadeLabel(); compile(); }
    else toast(`${name} is not part of this microcircuit (${pr?.neuronas.join(", ")}).`);
  });
  const tip = $("tooltip");
  scene.on("hover", (i, px) => {
    if (i < 0 || !px) { tip.classList.remove("show"); return; }
    const d = state.neurons[i];
    let p = "";
    if (state.walk) p = `<br>P(fire) = <b>${(100 * frameValues(state.frame).P[i]).toFixed(2)}%</b>`;
    tip.innerHTML = `<b>${d.name}</b> <span class="tag ${d.type}">${TYPE_ES[d.type]}</span><br>${d.degree} connections${p}` +
      `<br><span style="color:var(--faint)">click: fire the laser here</span>`;
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
    loaderText.textContent = "Reading the Cook et al. (2019) connectome in Python…";
    await respirar();
    const con = await py.conectoma(6000);
    state.neurons = con.neurons;
    ui.adj = con.neurons.map(() => []);
    for (const [i, j] of con.edges) { ui.adj[i].push(j); ui.adj[j].push(i); }
    con.neurons.forEach((d, i) => state.index.set(d.name, i));
    $("neuron-list").innerHTML = con.neurons.map((d) => `<option value="${d.name}">${TYPE_ES[d.type]}</option>`).join("");
    loaderText.textContent = "Loading the 3D body…";
    let glb = null;
    try { glb = await py.cuerpo(); } catch (e) { console.log(`No .glb body: ${e.message}`); }
    scene.setData(con.neurons, con.edges.slice(0, 1200), glb);

    const { microcircuitos } = await py.microcircuitos();
    state.presets = microcircuitos;
    $("preset").innerHTML = microcircuitos.map((m) =>
      `<option value="${m.id}">${esc(m.nombre)}${m.hardware ? " · recommended for hardware" : ""}</option>`).join("");
    $("preset-desc").textContent = selectedPreset()?.descripcion ?? "";

    if (BACKEND) {
      try { state.backend = await py.backendInfo(BACKEND); } catch (e) { console.log(`backend: ${e.message}`); }
    }
    renderBackendInfo();
    $("loader").classList.add("hide");
    neuronCard(state.source);
    console.log(`Optogenetic Quantum Brain ready · ${con.neurons.length} neurons · ${con.edges.length} synapses drawn` +
      (state.backend ? ` · backend ${state.backend.nombre}` : ""));
    await fire("AVM");
    await compile();
  } catch (e) {
    loaderText.textContent = `Could not start the Python core (${e.message}).`;
    $("backend-pill").textContent = "error";
    $("backend-pill").className = "pill err";
    console.log(`Startup error: ${e.stack || e.message}`);
  }
}

await init();

// La página sigue siendo interactiva (láser, microcircuito, envío del job) hasta que se
// presione Stop: se mantiene viva la ejecución para que Python siga disponible.
await new Promise(() => {});
