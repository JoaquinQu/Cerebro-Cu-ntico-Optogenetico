// Escena 3D: gusano C. elegans con sus 302 neuronas en posiciones reales (versión Qollab).
//
// Diferencias con frontend/js/scene.js: el lienzo vive dentro de un contenedor (no ocupa
// la ventana), el cuerpo .glb llega desde Python como bytes (JS no puede leer archivos
// del proyecto en Qollab), respeta prefers-reduced-motion y se maneja con teclado.
//
// Rendimiento (pensado para notebooks con gráficos integrados):
//   * render bajo demanda: sólo se dibuja cuando algo cambia (cámara, animación, láser);
//   * calidad alta / media / baja, con ajuste automático si los FPS caen;
//   * bloom a media resolución en "media" y desactivado en "baja";
//   * selección de neuronas en espacio de pantalla (sin raycasting por cuadro);
//   * colores por tabla precalculada y buffers tipados para neuronas y sinapsis.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const TYPE_COLOR = {
  sensory: new THREE.Color("#2dd4bf"),
  interneuron: new THREE.Color("#a78bfa"),
  motor: new THREE.Color("#f59e0b"),
  unknown: new THREE.Color("#94a3b8"),
};
const STOPS = [
  [0.0, new THREE.Color("#13204a")],
  [0.35, new THREE.Color("#1e6bff")],
  [0.7, new THREE.Color("#38e1ff")],
  [1.0, new THREE.Color("#ffffff")],
];
export function colormap(v, out = new THREE.Color()) {
  v = Math.min(1, Math.max(0, v));
  for (let i = 1; i < STOPS.length; i++) {
    if (v <= STOPS[i][0]) {
      const [a, ca] = STOPS[i - 1];
      const [b, cb] = STOPS[i];
      return out.copy(ca).lerp(cb, (v - a) / (b - a));
    }
  }
  return out.copy(STOPS[STOPS.length - 1][1]);
}
// Tabla de 256 colores precalculada (evita interpolar por neurona y por cuadro)
const LUT = (() => {
  const t = new Float32Array(256 * 3), c = new THREE.Color();
  for (let i = 0; i < 256; i++) { colormap(i / 255, c); t.set([c.r, c.g, c.b], i * 3); }
  return t;
})();
const lutIndex = (v) => 3 * Math.max(0, Math.min(255, Math.round(v * 255)));

const REDUCED_MOTION = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

const S_AP = 0.02; // µm → unidades de escena (eje anteroposterior)
const S_TR = 0.028; // ejes transversales (×1.4 respecto del real, para leer mejor el volumen)
const GLTF_SCALE = 0.01; // 1 unidad glTF = 100 µm  (ver docs/MODELO_3D.md)

export const QUALITY = {
  alta: { label: "High", pixelRatio: () => Math.min(window.devicePixelRatio, 1.75), bloom: true, bloomScale: 1 },
  media: { label: "Medium", pixelRatio: () => 1, bloom: true, bloomScale: 0.5 },
  baja: { label: "Low", pixelRatio: () => Math.min(window.devicePixelRatio, 1) * 0.85, bloom: false, bloomScale: 0 },
};

export class WormScene {
  constructor(canvas, { quality = "auto" } = {}) {
    this.canvas = canvas;
    this.container = canvas.parentElement;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.0;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color("#04060c");
    this.scene.fog = new THREE.FogExp2("#04060c", 0.025);

    this.camera = new THREE.PerspectiveCamera(40, 1, 0.05, 200);
    this.camera.position.set(-1.2, 6.0, 23.5);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 2.5;
    this.controls.maxDistance = 40;
    this.controls.autoRotate = false;
    this.controls.autoRotateSpeed = 0.35;
    this.controls.addEventListener("change", () => this.requestRender());

    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.75, 0.45, 0.28);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());

    this._last = performance.now();
    this.pointer = null;
    this.hovered = -1;
    this.callbacks = { pick: () => {}, hover: () => {}, quality: () => {}, key: () => {} };
    this.edgeVisible = true;
    this.laser = null;
    this.highlight = new Set();
    this._tmpMat = new THREE.Matrix4();
    this._tmpVec = new THREE.Vector3();
    this._dirty = true;
    this._perf = { frames: 0, time: 0, lastActive: 0 };

    this.autoQuality = quality === "auto";
    this.quality = this.autoQuality ? (window.devicePixelRatio > 1.5 ? "media" : "alta") : quality;

    this.reducedMotion = REDUCED_MOTION;
    this.glbBytes = null;
    this._addStars();
    this._bindEvents();
    this._resize();
    this.renderer.setAnimationLoop(() => this._tick());
  }

  on(name, fn) { this.callbacks[name] = fn; }
  requestRender() { this._dirty = true; }

  setQuality(q, { auto = false } = {}) {
    if (q === "auto") { this.autoQuality = true; q = this.quality; } else if (!auto) { this.autoQuality = false; }
    this.quality = q;
    this._resize();
    this.callbacks.quality(q, this.autoQuality);
  }

  setAutoRotate(v) { this.controls.autoRotate = v; this.requestRender(); }

  // ------------------------------------------------------------------ datos
  setData(neurons, edges, glbBytes = null) {
    this.glbBytes = glbBytes;
    this.neurons = neurons;
    const n = neurons.length;
    const c = [0, 0, 0];
    neurons.forEach((d) => { c[0] += d.x; c[2] += d.z; });
    c[0] /= n; c[2] /= n;
    const ys = neurons.map((d) => d.y);
    c[1] = (Math.min(...ys) + Math.max(...ys)) / 2; // centro del cuerpo (no de la cabeza)
    this.center = c;
    this.positions = neurons.map((d) => this.dataToScene(d.x, d.y, d.z));
    this.baseColors = neurons.map((d) => TYPE_COLOR[d.type] ?? TYPE_COLOR.unknown);

    // Neuronas (una sola llamada de dibujo)
    const mat = new THREE.MeshBasicMaterial({ toneMapped: false });
    this.mesh = new THREE.InstancedMesh(new THREE.SphereGeometry(0.055, 14, 10), mat, n);
    this.mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(n * 3), 3);
    this.scene.add(this.mesh);

    // Sinapsis (buffers tipados; peso normalizado para el brillo base)
    const m = edges.length;
    this.edgeA = new Int32Array(m);
    this.edgeB = new Int32Array(m);
    this.edgeW = new Float32Array(m);
    const wmax = Math.max(...edges.map((e) => e[2]), 1e-9);
    const ep = new Float32Array(m * 6);
    edges.forEach(([i, j, w], k) => {
      this.edgeA[k] = i; this.edgeB[k] = j; this.edgeW[k] = w / wmax;
      const a = this.positions[i], b = this.positions[j];
      ep.set([a.x, a.y, a.z, b.x, b.y, b.z], k * 6);
    });
    const eg = new THREE.BufferGeometry();
    eg.setAttribute("position", new THREE.BufferAttribute(ep, 3));
    eg.setAttribute("color", new THREE.BufferAttribute(new Float32Array(m * 6), 3));
    this.edgeLines = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.4, blending: THREE.AdditiveBlending,
      depthWrite: false, toneMapped: false,
    }));
    this.scene.add(this.edgeLines);

    this.ringGroup = new THREE.Group();
    this.scene.add(this.ringGroup);
    this._buildLabel();
    this._loadBody();
    this.setActivity(null);
  }

  dataToScene(x, y, z) {
    const c = this.center;
    return new THREE.Vector3((y - c[1]) * S_AP, (z - c[2]) * S_TR, (x - c[0]) * S_TR);
  }

  // ------------------------------------------------------------- cuerpo 3D
  _bodyMaterial(color, rim, strength = 1) {
    return new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
      uniforms: { uColor: { value: new THREE.Color(color) }, uRim: { value: new THREE.Color(rim) }, uK: { value: strength } },
      vertexShader: /* glsl */`
        varying vec3 vN; varying vec3 vV;
        void main(){
          vec4 mv = modelViewMatrix * vec4(position,1.0);
          vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */`
        uniform vec3 uColor; uniform vec3 uRim; uniform float uK;
        varying vec3 vN; varying vec3 vV;
        void main(){
          float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.6);
          vec3 c = mix(uColor, uRim, f) * (0.05 + 0.4*f) * uK;
          gl_FragColor = vec4(c, (0.16*f + 0.015) * uK);
        }`,
    });
  }

  async _loadBody() {
    // 1) Modelo anatómico (data/gusano.glb, que Python lee y entrega como bytes)
    try {
      if (!this.glbBytes) throw new Error("no .glb model");
      const gltf = await new GLTFLoader().parseAsync(this.glbBytes, "");
      const group = new THREE.Group();
      gltf.scene.updateMatrixWorld(true);
      gltf.scene.traverse((obj) => {
        if (!obj.isMesh) return;
        const geo = obj.geometry.clone();
        geo.applyMatrix4(obj.matrixWorld);
        const p = geo.attributes.position;
        for (let i = 0; i < p.count; i++) {
          // glTF (X, Y, Z) = (x, z, −y)·0.01  →  datos (µm)  →  escena
          const v = this.dataToScene(p.getX(i) / GLTF_SCALE, -p.getZ(i) / GLTF_SCALE, p.getY(i) / GLTF_SCALE);
          p.setXYZ(i, v.x, v.y, v.z);
        }
        geo.deleteAttribute("normal");
        geo.computeVertexNormals();
        const name = `${obj.name} ${obj.material?.name ?? ""}`.toLowerCase();
        const inner = /faringe|pharynx|intestin|gut/.test(name);
        group.add(new THREE.Mesh(geo, inner
          ? this._bodyMaterial("#4fb3ff", "#bff3ff", 0.75)
          : this._bodyMaterial("#2a6dff", "#7fe8ff", 1.0)));
      });
      if (!group.children.length) throw new Error("empty glb");
      this.body = group;
      this.scene.add(group);
      this.bodySource = "glb";
    } catch (err) {
      // 2) Respaldo: cuerpo aproximado generado aquí mismo
      console.info("Using procedural body:", err?.message ?? err);
      this._buildProceduralBody();
      this.bodySource = "procedural";
    }
    this.requestRender();
  }

  _buildProceduralBody() {
    const xs = this.positions.map((p) => p.x);
    const x0 = Math.min(...xs) - 0.35, x1 = Math.max(...xs) + 0.45;
    const bins = 48, seg = 40;
    const centers = [], radii = [];
    for (let b = 0; b <= bins; b++) {
      const x = x0 + ((x1 - x0) * b) / bins;
      const near = this.positions.filter((p) => Math.abs(p.x - x) < 0.6);
      let cy = 0, cz = 0;
      if (near.length) { near.forEach((p) => { cy += p.y; cz += p.z; }); cy /= near.length; cz /= near.length; }
      let r = 0.18;
      near.forEach((p) => { r = Math.max(r, Math.hypot(p.y - cy, p.z - cz)); });
      centers.push([x, cy, cz]);
      radii.push(r);
    }
    const smooth = (arr, k) => arr.map((_, i) => {
      let s = 0, c = 0;
      for (let d = -k; d <= k; d++) { const j = i + d; if (j >= 0 && j < arr.length) { s += arr[j]; c++; } }
      return s / c;
    });
    const ys = smooth(centers.map((c) => c[1]), 3), zs = smooth(centers.map((c) => c[2]), 3);
    const rs = smooth(radii, 4).map((r, i) => (r * 1.12 + 0.12) * Math.pow(Math.sin((Math.PI * i) / bins), 0.45) + 0.02);
    const pos = [], idx = [];
    for (let b = 0; b <= bins; b++) {
      for (let k = 0; k <= seg; k++) {
        const a = (k / seg) * Math.PI * 2;
        pos.push(centers[b][0], ys[b] + rs[b] * Math.cos(a), zs[b] + rs[b] * Math.sin(a));
      }
    }
    for (let b = 0; b < bins; b++) {
      for (let k = 0; k < seg; k++) {
        const i0 = b * (seg + 1) + k, i1 = i0 + seg + 1;
        idx.push(i0, i1, i0 + 1, i1, i1 + 1, i0 + 1);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    g.computeVertexNormals();
    this.body = new THREE.Mesh(g, this._bodyMaterial("#2a6dff", "#7fe8ff"));
    this.scene.add(this.body);
  }

  // --------------------------------------------------------------- resaltes
  setHighlight(indices) {
    this.highlight = new Set(indices);
    this.ringGroup.clear();
    const geo = new THREE.RingGeometry(0.13, 0.16, 32);
    const mat = new THREE.MeshBasicMaterial({ color: "#ffd166", transparent: true, opacity: 0.85,
      side: THREE.DoubleSide, toneMapped: false, depthWrite: false });
    for (const i of indices) {
      const m = new THREE.Mesh(geo, mat);
      m.position.copy(this.positions[i]);
      this.ringGroup.add(m);
    }
    if (this.activity !== undefined) this.setActivity(this.activity);
  }

  /** Rastro de la cascada: línea que une los centros sucesivos (índices de neuronas). */
  setTrail(indices) {
    if (this.trail) {
      this.scene.remove(this.trail);
      this.trail.geometry.dispose();
      this.trail.material.dispose();
      this.trail = null;
    }
    if (indices && indices.length >= 2) {
      const g = new THREE.BufferGeometry().setFromPoints(indices.map((i) => this.positions[i]));
      this.trail = new THREE.Line(g, new THREE.LineBasicMaterial({ color: new THREE.Color("#ffb347").multiplyScalar(1.4),
        transparent: true, opacity: 0.95, toneMapped: false, depthWrite: false }));
      this.scene.add(this.trail);
    }
    this.requestRender();
  }

  _buildLabel() {
    this.labelEl = document.createElement("div");
    Object.assign(this.labelEl.style, {
      position: "absolute", pointerEvents: "none", zIndex: 4, font: "600 12px var(--mono)", color: "#cfe9ff",
      textShadow: "0 0 8px rgba(56,225,255,.9)", transform: "translate(-50%, -160%)", whiteSpace: "nowrap",
    });
    this.labelEl.className = "neuron-label";
    this.labelEl.setAttribute("aria-hidden", "true");
    this.container.appendChild(this.labelEl);
    this.labelIndex = -1;
  }

  setLabel(index, text) { this.labelIndex = index; this.labelEl.textContent = text ?? ""; this.requestRender(); }

  // ---------------------------------------------------------------- actividad
  setActivity(values) {
    this.activity = values;
    const n = this.neurons.length;
    const col = this.mesh.instanceColor.array;
    const M = this._tmpMat.elements;
    for (let i = 0; i < n; i++) {
      const v = values ? values[i] : 0;
      const base = this.baseColors[i];
      let r, g, b, s;
      if (v > 0.015) {
        const li = lutIndex(v);
        const boost = 0.45 + 1.7 * v;
        const mix = Math.max(0, 0.25 - v);
        r = LUT[li] * boost * (1 - mix) + base.r * mix;
        g = LUT[li + 1] * boost * (1 - mix) + base.g * mix;
        b = LUT[li + 2] * boost * (1 - mix) + base.b * mix;
        s = 1 + 2.4 * Math.sqrt(v);
      } else {
        r = base.r * 0.33; g = base.g * 0.33; b = base.b * 0.33; s = 1;
      }
      if (this.highlight.has(i)) s *= 1.15;
      col[i * 3] = r; col[i * 3 + 1] = g; col[i * 3 + 2] = b;
      const p = this.positions[i];
      this._tmpMat.identity();
      M[0] = s; M[5] = s; M[10] = s; M[12] = p.x; M[13] = p.y; M[14] = p.z;
      this.mesh.setMatrixAt(i, this._tmpMat);
    }
    this.mesh.instanceColor.needsUpdate = true;
    this.mesh.instanceMatrix.needsUpdate = true;

    if (this.edgeVisible) this._updateEdges(values);
    this.requestRender();
  }

  _updateEdges(values) {
    const ec = this.edgeLines.geometry.attributes.color.array;
    const A = this.edgeA, B = this.edgeB, W = this.edgeW;
    for (let k = 0; k < A.length; k++) {
      const act = values ? Math.sqrt(values[A[k]] * values[B[k]]) : 0;
      const base = 0.25 + 0.75 * W[k];
      const li = lutIndex(0.45 + 0.55 * act);
      const k2 = act * base * 0.55;
      const r = 0.025 * base + LUT[li] * k2, g = 0.04 * base + LUT[li + 1] * k2, b = 0.09 * base + LUT[li + 2] * k2;
      const o = k * 6;
      ec[o] = r; ec[o + 1] = g; ec[o + 2] = b; ec[o + 3] = r; ec[o + 4] = g; ec[o + 5] = b;
    }
    this.edgeLines.geometry.attributes.color.needsUpdate = true;
  }

  setEdgesVisible(v) {
    this.edgeVisible = v;
    if (this.edgeLines) {
      this.edgeLines.visible = v;
      if (v) this._updateEdges(this.activity);
    }
    this.requestRender();
  }

  // ------------------------------------------------------------------- láser
  fireLaser(index, intensity = 1) {
    const target = this.positions[index];
    if (this.laser) this.scene.remove(this.laser.group);
    const group = new THREE.Group();
    const from = target.clone().add(new THREE.Vector3(-0.6, 4.5, 1.2));
    const dir = target.clone().sub(from);
    const len = dir.length();
    const mk = (r, color, op) => {
      const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r * 0.6, len, 12, 1, true),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: op, blending: THREE.AdditiveBlending,
          depthWrite: false, toneMapped: false }));
      m.position.copy(from).addScaledVector(dir, 0.5);
      m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize());
      return m;
    };
    const glow = mk(0.07, new THREE.Color("#4da3ff").multiplyScalar(1.6), 0.3);
    const core = mk(0.014, new THREE.Color("#e8f4ff").multiplyScalar(2), 0.9);
    const flash = new THREE.Mesh(new THREE.SphereGeometry(0.3, 16, 12), new THREE.MeshBasicMaterial({
      color: new THREE.Color("#7cc4ff").multiplyScalar(3), transparent: true, opacity: 0.8,
      blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }));
    flash.position.copy(target);
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.2, 0.24, 48), new THREE.MeshBasicMaterial({
      color: new THREE.Color("#4da3ff").multiplyScalar(2.5), transparent: true, opacity: 0.9,
      side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }));
    ring.position.copy(target);
    group.add(glow, core, flash, ring);
    this.scene.add(group);
    this.laser = { group, glow, core, flash, ring, t: 0, intensity };
  }

  _animateLaser(dt) {
    const L = this.laser;
    if (!L) return false;
    L.t += dt;
    const on = Math.min(1, L.t / 0.15) * Math.max(0, 1 - Math.max(0, L.t - 0.9) / 0.6);
    const k = 0.35 + 0.65 * L.intensity;
    const flicker = this.reducedMotion ? 1 : 0.85 + 0.15 * Math.sin(L.t * 40);
    L.glow.material.opacity = 0.35 * on * k * flicker;
    L.core.material.opacity = 0.95 * on * k;
    L.flash.material.opacity = 0.8 * on * k;
    L.flash.scale.setScalar(0.6 + 0.4 * Math.sin(Math.min(L.t, 1.2) * 6));
    L.ring.scale.setScalar(1 + L.t * 5);
    L.ring.material.opacity = Math.max(0, 0.9 - L.t * 0.7);
    L.ring.lookAt(this.camera.position);
    if (L.t > 1.6) {
      this.scene.remove(L.group);
      L.group.traverse((o) => { o.geometry?.dispose(); o.material?.dispose(); });
      this.laser = null;
    }
    return true;
  }

  // ---------------------------------------------------------- medición (colapso)
  /**
   * Animación de la medida de un paso de la cascada.
   *  fase 1 (superposición): las neuronas de la ventana laten juntas, con halos ∝ √p;
   *  fase 2 (colapso): partículas viajan desde cada neurona hasta la que salió en 1, los demás
   *  halos se apagan y la elegida destella. Si no hubo spike (vacío), todo se desvanece.
   * Devuelve una promesa que se resuelve al terminar (inmediata con prefers-reduced-motion).
   */
  collapse(windowIdx, probs, spikeIdx, { superposition = 0.9, collapse = 0.75 } = {}) {
    this._endCollapse();
    if (this.reducedMotion || !this.positions || !windowIdx?.length) return Promise.resolve();
    const tot = probs.reduce((a, b) => a + Math.max(0, b), 0) || 1;
    const p = probs.map((v) => Math.max(0, v) / tot);
    const pmax = Math.max(...p, 1e-9);
    const group = new THREE.Group();
    const add = (c, o) => new THREE.MeshBasicMaterial({ color: c, transparent: true, opacity: o,
      blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false });
    const haloGeo = new THREE.SphereGeometry(0.22, 18, 12);
    const halos = windowIdx.map((g, i) => {
      const m = new THREE.Mesh(haloGeo, add(new THREE.Color("#38e1ff").multiplyScalar(1.3), 0));
      m.position.copy(this.positions[g]);
      m.userData = { r: 0.35 + 1.25 * Math.sqrt(p[i] / pmax), ph: i * 0.7 };
      group.add(m);
      return m;
    });
    // partículas: más cuanto más probable era cada neurona
    const starts = [];
    windowIdx.forEach((g, i) => {
      const n = 3 + Math.round(14 * p[i] / pmax);
      for (let k = 0; k < n; k++) {
        const j = new THREE.Vector3((Math.random() - 0.5) * 0.3, (Math.random() - 0.5) * 0.3, (Math.random() - 0.5) * 0.3);
        starts.push({ from: this.positions[g].clone().add(j), delay: Math.random() * 0.25 });
      }
    });
    const pp = new Float32Array(starts.length * 3);
    const pg = new THREE.BufferGeometry();
    pg.setAttribute("position", new THREE.BufferAttribute(pp, 3));
    const pts = new THREE.Points(pg, new THREE.PointsMaterial({ color: new THREE.Color("#ffd28a").multiplyScalar(1.6), size: 0.11,
      transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }));
    group.add(pts);
    // destello final sobre la neurona medida
    const target = spikeIdx != null ? this.positions[spikeIdx] : null;
    const flash = new THREE.Mesh(new THREE.SphereGeometry(0.3, 18, 12), add(new THREE.Color("#ffb347").multiplyScalar(2.6), 0));
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.24, 0.29, 48), add(new THREE.Color("#ffb347").multiplyScalar(2.2), 0));
    ring.material.side = THREE.DoubleSide;
    if (target) { flash.position.copy(target); ring.position.copy(target); group.add(flash, ring); }
    this.scene.add(group);

    const N = this.neurons.length;
    const vals = new Float32Array(N);
    const base = this.activity ? Float32Array.from(this.activity) : new Float32Array(N);
    return new Promise((resolve) => {
      this._collapse = {
        t: 0, group, resolve,
        update: (dt) => {
          const C = this._collapse;
          C.t += dt;
          const t = C.t, T1 = superposition, T2 = superposition + collapse, TAIL = 0.45;
          if (t >= T2) {
            // cola: la actividad ya la decide main.js; sólo se apaga el destello
            if (!C.done) { C.done = true; pts.visible = false; halos.forEach((h) => { h.visible = false; }); resolve(); }
            const v = Math.min(1, (t - T2) / TAIL);
            flash.material.opacity = 0.9 * (1 - v);
            ring.material.opacity = 0.9 * (1 - v);
            ring.scale.setScalar(3.5 + 2 * v);
            ring.lookAt(this.camera.position);
            if (v >= 1) { this._endCollapse(); return false; }
            return true;
          }
          vals.set(base);
          for (let i = 0; i < N; i++) vals[i] *= 0.35;
          if (t < T1) {
            // fase 1: superposición (todas a la vez, latiendo)
            const a = Math.min(1, t / 0.25);
            windowIdx.forEach((g, i) => {
              const beat = 0.75 + 0.25 * Math.sin(t * 9 + halos[i].userData.ph);
              vals[g] = Math.min(1, (0.35 + 0.65 * Math.sqrt(p[i] / pmax)) * beat * a);
              halos[i].scale.setScalar(halos[i].userData.r * (0.85 + 0.2 * beat));
              halos[i].material.opacity = 0.45 * a * (0.35 + 0.65 * Math.sqrt(p[i] / pmax));
            });
          } else {
            // fase 2: colapso
            const u = Math.min(1, (t - T1) / collapse);
            const fade = 1 - u;
            windowIdx.forEach((g, i) => {
              const own = g === spikeIdx;
              vals[g] = own ? Math.min(1, 0.6 + 0.4 * u) : Math.max(0.04, (0.35 + 0.65 * Math.sqrt(p[i] / pmax)) * fade * fade);
              halos[i].material.opacity = own ? 0.45 * fade : 0.45 * fade * fade * (0.35 + 0.65 * Math.sqrt(p[i] / pmax));
            });
            if (target) {
              pts.material.opacity = Math.min(1, 3 * u) * (u < 0.85 ? 1 : (1 - u) / 0.15);
              starts.forEach((s, k) => {
                const v = Math.max(0, Math.min(1, (u - s.delay) / (1 - s.delay)));
                const e = v * v * (3 - 2 * v);
                pp[k * 3] = s.from.x + (target.x - s.from.x) * e;
                pp[k * 3 + 1] = s.from.y + (target.y - s.from.y) * e + Math.sin(Math.PI * e) * 0.25;
                pp[k * 3 + 2] = s.from.z + (target.z - s.from.z) * e;
              });
              pg.attributes.position.needsUpdate = true;
              const f = Math.max(0, (u - 0.6) / 0.4);
              flash.material.opacity = 0.9 * f;
              flash.scale.setScalar(0.5 + 0.9 * f);
              ring.material.opacity = 0.9 * f;
              ring.scale.setScalar(1 + 2.5 * f);
              ring.lookAt(this.camera.position);
            }
          }
          this.setActivity(vals);
          return true;
        },
      };
    });
  }

  _endCollapse() {
    const C = this._collapse;
    if (!C) return;
    this._collapse = null;
    this.scene.remove(C.group);
    C.group.traverse((o) => { o.geometry?.dispose(); o.material?.dispose(); });
    this.requestRender();
    C.resolve();
  }

  resetView() {
    this.camera.position.set(-1.2, 6.0, 23.5);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
    this.requestRender();
  }

  _dolly(f) {
    const off = this.camera.position.clone().sub(this.controls.target).multiplyScalar(f);
    const d = Math.min(this.controls.maxDistance, Math.max(this.controls.minDistance, off.length()));
    this.camera.position.copy(this.controls.target).add(off.setLength(d));
    this.requestRender();
  }

  _orbit(angle) {
    const off = this.camera.position.clone().sub(this.controls.target);
    off.applyAxisAngle(new THREE.Vector3(0, 1, 0), angle);
    this.camera.position.copy(this.controls.target).add(off);
    this.requestRender();
  }

  focus(index) { this._focusTarget = this.positions[index].clone(); this.requestRender(); }

  // ---------------------------------------------------------------- interno
  _addStars() {
    const n = 900;
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const r = 30 + Math.random() * 60, th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
      pos.set([r * Math.sin(ph) * Math.cos(th), r * Math.cos(ph), r * Math.sin(ph) * Math.sin(th)], i * 3);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this.scene.add(new THREE.Points(g, new THREE.PointsMaterial({ color: "#5d74b8", size: 0.12, transparent: true,
      opacity: 0.55, depthWrite: false })));
  }

  _bindEvents() {
    if (typeof ResizeObserver === "function") new ResizeObserver(() => this._resize()).observe(this.container);
    window.addEventListener("resize", () => this._resize());
    const local = (e) => { const r = this.canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    this.canvas.addEventListener("pointermove", (e) => { this.pointer = local(e); this._pointerMoved = true; });
    this.canvas.addEventListener("pointerleave", () => { this.pointer = null; this._pointerMoved = true; });
    let down = null;
    this.canvas.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY]; });
    this.canvas.addEventListener("pointerup", (e) => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
      const [x, y] = local(e);
      const idx = this._pick(x, y);
      if (idx >= 0) this.callbacks.pick(idx);
    });
    document.addEventListener("visibilitychange", () => { if (!document.hidden) this.requestRender(); });
    // Teclado (con el foco en el lienzo): el resto lo decide main.js
    this.canvas.addEventListener("keydown", (e) => {
      if (e.key === "r" || e.key === "R") { this.resetView(); e.preventDefault(); return; }
      if (e.key === "+" || e.key === "=") { this._dolly(0.85); e.preventDefault(); return; }
      if (e.key === "-") { this._dolly(1.18); e.preventDefault(); return; }
      if (e.key === "ArrowUp" || e.key === "ArrowDown") { this._orbit(e.key === "ArrowUp" ? -0.12 : 0.12); e.preventDefault(); return; }
      if (this.callbacks.key(e)) e.preventDefault();
    });
  }

  /** Neurona más cercana al puntero en pantalla (≤ 14 px). O(302), sin raycasting. */
  _pick(px, py) {
    if (!this.positions) return -1;
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    let best = -1, bestD = 14 * 14, bestZ = Infinity;
    for (let i = 0; i < this.positions.length; i++) {
      const p = this._tmpVec.copy(this.positions[i]).project(this.camera);
      if (p.z > 1) continue;
      const dx = (p.x * 0.5 + 0.5) * w - px, dy = (-p.y * 0.5 + 0.5) * h - py;
      const d = dx * dx + dy * dy;
      if (d < bestD || (d < 14 * 14 && Math.abs(d - bestD) < 4 && p.z < bestZ)) { best = i; bestD = d; bestZ = p.z; }
    }
    return best;
  }

  _resize() {
    const w = Math.max(1, this.container.clientWidth), h = Math.max(1, this.container.clientHeight);
    const Q = QUALITY[this.quality];
    const pr = Q.pixelRatio();
    this.renderer.setPixelRatio(pr);
    this.renderer.setSize(w, h, false);
    this.composer.setPixelRatio(pr);
    this.composer.setSize(w, h);
    if (Q.bloom) this.bloom.setSize(Math.round(w * pr * Q.bloomScale), Math.round(h * pr * Q.bloomScale));
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.requestRender();
  }

  _adaptQuality(dt, active) {
    const P = this._perf;
    if (!this.autoQuality || !active) { P.frames = 0; P.time = 0; return; }
    if (dt > 0.5) return; // pestaña en segundo plano o pausa larga: no cuenta
    P.frames++;
    P.time += dt;
    if (P.time > 2.0) {
      const fps = P.frames / P.time;
      P.frames = 0; P.time = 0;
      const order = ["alta", "media", "baja"];
      const i = order.indexOf(this.quality);
      if (fps < 28 && i < 2) this.setQuality(order[i + 1], { auto: true });
    }
  }

  _tick() {
    const now = performance.now();
    const rawDt = (now - this._last) / 1000;
    this._last = now;
    const dt = Math.min(0.1, rawDt);
    let active = false;
    if (this._focusTarget) {
      this.controls.target.lerp(this._focusTarget, 0.08);
      if (this.controls.target.distanceTo(this._focusTarget) < 0.01) this._focusTarget = null;
      active = true;
    }
    if (this.controls.update()) active = true; // amortiguación / rotación automática
    if (this._animateLaser(dt)) active = true;
    if (this._collapse && this._collapse.update(dt)) active = true;

    if (this._pointerMoved) {
      this._pointerMoved = false;
      const idx = this.pointer ? this._pick(this.pointer[0], this.pointer[1]) : -1;
      if (idx !== this.hovered) {
        this.hovered = idx;
        this.canvas.style.cursor = idx >= 0 ? "pointer" : "grab";
      }
      this.callbacks.hover(idx, this.pointer);
    }

    if (!(active || this._dirty)) return; // nada cambió: no se dibuja (ahorra GPU y batería)
    this._dirty = false;
    if (this.ringGroup) this.ringGroup.children.forEach((m) => m.quaternion.copy(this.camera.quaternion));
    if (this.labelIndex >= 0 && this.positions) {
      const p = this._tmpVec.copy(this.positions[this.labelIndex]).project(this.camera);
      this.labelEl.style.display = p.z < 1 ? "block" : "none";
      this.labelEl.style.left = `${(p.x * 0.5 + 0.5) * this.canvas.clientWidth}px`;
      this.labelEl.style.top = `${(-p.y * 0.5 + 0.5) * this.canvas.clientHeight}px`;
    }
    if (QUALITY[this.quality].bloom) this.composer.render(dt);
    else this.renderer.render(this.scene, this.camera);
    this._adaptQuality(rawDt, active || this._continuous);
  }

  /** main.js avisa cuando hay una animación en curso (para medir FPS sólo en ese caso). */
  setContinuous(v) { this._continuous = v; }
}
