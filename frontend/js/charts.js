// Gráficos SVG livianos (sin dependencias): barras agrupadas y series temporales.
const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, parent) => {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
};

export const SERIES_COLORS = {
  exact: "#ffffff",
  ideal: "#38e1ff",
  noisy: "#a78bfa",
  ionq: "#ffb347",
};

/** Barras agrupadas: labels = neuronas, series = [{key, name, values}] */
export function groupedBars(container, labels, series, { height = 170, max = null, highlight = [] } = {}) {
  container.innerHTML = "";
  const many = labels.length > 8;
  const W = 330, padL = 28, padT = 8, padB = many ? 44 : 30, H = height + (many ? 14 : 0);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" }, container);
  const ymax = max ?? Math.max(0.05, ...series.flatMap((s) => s.values)) * 1.1;
  const plotW = W - padL - 4, plotH = H - padB - padT;
  const g = el("g", { class: "axis" }, svg);
  [0, 0.25, 0.5, 0.75, 1].forEach((f) => {
    const y = padT + plotH * (1 - f);
    el("line", { x1: padL, x2: W - 4, y1: y, y2: y, "stroke-dasharray": f === 0 ? "" : "2 3" }, g);
    const t = el("text", { x: padL - 5, y: y + 3, "text-anchor": "end" }, g);
    t.textContent = (ymax * f).toFixed(2);
  });
  const groupW = plotW / labels.length;
  const barW = Math.min(9, (groupW - 6) / series.length);
  labels.forEach((lab, i) => {
    const x0 = padL + groupW * i + (groupW - barW * series.length) / 2;
    series.forEach((s, k) => {
      const v = s.values[i] ?? 0;
      const h = (plotH * v) / ymax;
      const r = el("rect", {
        x: x0 + k * barW, y: padT + plotH - h, width: barW - 1.2, height: Math.max(0, h), rx: 1.5,
        fill: SERIES_COLORS[s.key] ?? "#888", opacity: s.key === "exact" ? 0.92 : 0.88,
      }, svg);
      const tt = el("title", {}, r);
      tt.textContent = `${lab} · ${s.name}: ${v.toFixed(3)}`;
    });
    const lx = padL + groupW * (i + 0.5), ly = many ? H - padB + 12 : H - 12;
    const t = el("text", many
      ? { x: lx, y: ly, "text-anchor": "end", transform: `rotate(-50 ${lx} ${ly})` }
      : { x: lx, y: ly, "text-anchor": "middle" }, svg);
    t.textContent = lab;
    t.setAttribute("fill", highlight.includes(i) ? "#ffd166" : "#8c97b5");
    t.setAttribute("font-size", "9.5");
  });
}

/** Series temporales de poblaciones con marcador vertical en t */
export function timeSeries(container, times, rows, labels, { marker = null, height = 120, colors = null } = {}) {
  container.innerHTML = "";
  const W = 330, H = height, padL = 28, padB = 18, padT = 6;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}` }, container);
  const tmax = times[times.length - 1] || 1;
  const plotW = W - padL - 6, plotH = H - padB - padT;
  const X = (t) => padL + (plotW * t) / tmax;
  const Y = (v) => padT + plotH * (1 - v);
  const g = el("g", { class: "axis" }, svg);
  el("line", { x1: padL, x2: W - 6, y1: Y(0), y2: Y(0) }, g);
  [0, 0.5, 1].forEach((v) => {
    const t = el("text", { x: padL - 5, y: Y(v) + 3, "text-anchor": "end" }, g);
    t.textContent = v.toFixed(1);
  });
  [0, 0.5, 1].forEach((f) => {
    const t = el("text", { x: X(tmax * f), y: H - 4, "text-anchor": "middle" }, g);
    t.textContent = (tmax * f).toFixed(0);
  });
  const palette = colors ?? ["#ffffff", "#38e1ff", "#a78bfa", "#2dd4bf", "#ffb347", "#ff6b81", "#7dd3fc",
    "#c4b5fd", "#fcd34d", "#86efac", "#f9a8d4", "#fdba74", "#93c5fd", "#d8b4fe"];
  labels.forEach((lab, k) => {
    const d = times.map((t, i) => `${i ? "L" : "M"}${X(t).toFixed(1)},${Y(rows[i][k]).toFixed(1)}`).join("");
    const p = el("path", { d, fill: "none", stroke: palette[k % palette.length], "stroke-width": 1.5, opacity: 0.9 }, svg);
    const tt = el("title", {}, p);
    tt.textContent = lab;
  });
  if (marker != null) {
    el("line", { x1: X(marker), x2: X(marker), y1: padT, y2: Y(0), stroke: "#ffd166", "stroke-dasharray": "3 3" }, svg);
  }
  return palette;
}

/** Diagrama del circuito lógico: láser (RX) y saltos hop(α) entre neuronas */
export function circuitDiagram(container, circuit) {
  container.innerHTML = "";
  const n = circuit.n_qubits, labels = circuit.labels;
  const gates = circuit.gates;
  // empaquetar en columnas (capas) sin solapamiento
  const busyUntil = new Array(n).fill(0);
  const placed = gates.map((g) => {
    const lo = Math.min(...g.qubits), hi = Math.max(...g.qubits);
    let col = 0;
    for (let q = lo; q <= hi; q++) col = Math.max(col, busyUntil[q]);
    for (let q = lo; q <= hi; q++) busyUntil[q] = col + 1;
    return { ...g, col, lo, hi };
  });
  const cols = Math.max(1, ...busyUntil);
  const dx = 22, dy = 22, padL = 46, padT = 12;
  const W = padL + cols * dx + 20, H = padT * 2 + (n - 1) * dy + 10;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H }, container);
  const y = (q) => padT + q * dy;
  for (let q = 0; q < n; q++) {
    el("line", { x1: padL - 6, x2: W - 8, y1: y(q), y2: y(q), stroke: "rgba(255,255,255,.18)" }, svg);
    const t = el("text", { x: padL - 10, y: y(q) + 3.5, "text-anchor": "end", "font-size": 9.5, fill: "#8c97b5" }, svg);
    t.textContent = labels?.[q] ?? `q${q}`;
  }
  const maxA = Math.max(1e-9, ...gates.filter((g) => g.name === "hop").map((g) => Math.abs(g.params[0])));
  placed.forEach((g) => {
    const x = padL + g.col * dx + dx / 2;
    if (g.name === "rx") {
      const c = el("circle", { cx: x, cy: y(g.qubits[0]), r: 7.5, fill: "#1e6bff", stroke: "#7cc4ff" }, svg);
      el("title", {}, c).textContent = `Láser RX(θ=${g.params[0].toFixed(3)})`;
      const t = el("text", { x, y: y(g.qubits[0]) + 3, "text-anchor": "middle", "font-size": 7.5, fill: "#fff" }, svg);
      t.textContent = "θ";
    } else if (g.name === "hop") {
      const a = Math.abs(g.params[0]) / maxA;
      const color = g.tag?.startsWith("givens") ? "#ffb347" : "#38e1ff";
      el("line", { x1: x, x2: x, y1: y(g.lo), y2: y(g.hi), stroke: color, "stroke-width": 1 + 1.5 * a, opacity: 0.85 }, svg);
      g.qubits.forEach((q) => {
        const c = el("circle", { cx: x, cy: y(q), r: 3.6, fill: color }, svg);
        el("title", {}, c).textContent = `hop(α=${g.params[0].toFixed(4)}) · ${labels[g.qubits[0]]}↔${labels[g.qubits[1]]} · ${g.tag}`;
      });
    }
  });
}
