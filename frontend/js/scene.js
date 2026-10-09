// Escena 3D: gusano C. elegans con sus 302 neuronas en posiciones reales.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

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

const S_AP = 0.02; // µm → unidades de escena (eje anteroposterior)
const S_TR = 0.028; // ejes transversales (×1.4 respecto del real; el gusano se ve "inflado" para leerlo)

export class WormScene {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
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
    this.controls.autoRotate = true;
    this.controls.autoRotateSpeed = 0.25;

    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.75, 0.45, 0.28);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());

    this.clock = new THREE.Clock();
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2(2, 2);
    this.hovered = -1;
    this.callbacks = { pick: () => {}, hover: () => {} };
    this.activity = null;
    this.edgeVisible = true;
    this.laser = null;
    this.highlight = new Set();
    this._tmpColor = new THREE.Color();
    this._tmpMat = new THREE.Matrix4();
    this._tmpVec = new THREE.Vector3();

    this._addStars();
    this._bindEvents();
    this._resize();
    this.renderer.setAnimationLoop(() => this._tick());
  }

  on(name, fn) { this.callbacks[name] = fn; }

  // ------------------------------------------------------------------ datos
  setData(neurons, edges) {
    this.neurons = neurons;
    const n = neurons.length;
    const mean = neurons.reduce((a, d) => [a[0] + d.x, a[1] + d.y, a[2] + d.z], [0, 0, 0]).map((v) => v / n);
    // centrar el eje anteroposterior en el punto medio del cuerpo (no en la cabeza, donde hay más neuronas)
    const ys = neurons.map((d) => d.y);
    mean[1] = (Math.min(...ys) + Math.max(...ys)) / 2;
    this.positions = neurons.map((d) => new THREE.Vector3(
      (d.y - mean[1]) * S_AP, (d.z - mean[2]) * S_TR, (d.x - mean[0]) * S_TR,
    ));
    this.baseColors = neurons.map((d) => TYPE_COLOR[d.type] ?? TYPE_COLOR.unknown);

    // Neuronas
    const geo = new THREE.SphereGeometry(0.055, 18, 12);
    const mat = new THREE.MeshBasicMaterial({ toneMapped: false });
    this.mesh = new THREE.InstancedMesh(geo, mat, n);
    this.mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(n * 3), 3);
    this.scene.add(this.mesh);

    // Esferas invisibles más grandes para facilitar el clic
    this.pickMesh = new THREE.InstancedMesh(new THREE.SphereGeometry(0.16, 8, 6),
      new THREE.MeshBasicMaterial({ visible: false }), n);
    this.positions.forEach((p, i) => {
      this._tmpMat.makeTranslation(p.x, p.y, p.z);
      this.pickMesh.setMatrixAt(i, this._tmpMat);
    });
    this.scene.add(this.pickMesh);

    // Sinapsis (peso normalizado al máximo para el brillo base)
    this.edges = edges;
    const wmax = Math.max(...edges.map((e) => e[2]), 1e-9);
    this.edgeW = edges.map((e) => e[2] / wmax);
    const ep = new Float32Array(edges.length * 6);
    edges.forEach(([i, j], k) => {
      const a = this.positions[i], b = this.positions[j];
      ep.set([a.x, a.y, a.z, b.x, b.y, b.z], k * 6);
    });
    const eg = new THREE.BufferGeometry();
    eg.setAttribute("position", new THREE.BufferAttribute(ep, 3));
    eg.setAttribute("color", new THREE.BufferAttribute(new Float32Array(edges.length * 6), 3));
    this.edgeLines = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.4, blending: THREE.AdditiveBlending,
      depthWrite: false, toneMapped: false,
    }));
    this.scene.add(this.edgeLines);

    this._buildBody();
    this._buildHighlightRings();
    this._buildLabel();
    this.setActivity(null);
  }

  _buildBody() {
    // Línea media y radio a partir de la propia nube de neuronas (por tramos a lo largo del cuerpo)
    const xs = this.positions.map((p) => p.x);
    const x0 = Math.min(...xs) - 0.35, x1 = Math.max(...xs) + 0.45;
    const bins = 48;
    const centers = [], radii = [];
    for (let b = 0; b <= bins; b++) {
      const x = x0 + ((x1 - x0) * b) / bins;
      const w = 0.6;
      const near = this.positions.filter((p) => Math.abs(p.x - x) < w);
      let cy = 0, cz = 0;
      if (near.length) { near.forEach((p) => { cy += p.y; cz += p.z; }); cy /= near.length; cz /= near.length; }
      let r = 0.18;
      near.forEach((p) => { r = Math.max(r, Math.hypot(p.y - cy, p.z - cz)); });
      centers.push(new THREE.Vector3(x, cy, cz));
      radii.push(r);
    }
    // suavizado
    const smooth = (arr, k = 3) => arr.map((_, i) => {
      let s = 0, c = 0;
      for (let d = -k; d <= k; d++) { const j = i + d; if (j >= 0 && j < arr.length) { s += arr[j]; c++; } }
      return s / c;
    });
    const ys = smooth(centers.map((c) => c.y)), zs = smooth(centers.map((c) => c.z));
    let rs = smooth(radii, 4);
    rs = rs.map((r, i) => {
      const s = i / bins;
      const cap = Math.pow(Math.sin(Math.PI * Math.min(1, Math.max(0, s))), 0.45);
      return (r * 1.12 + 0.12) * cap + 0.02;
    });
    const seg = 40;
    const pos = [], nor = [], idx = [];
    for (let b = 0; b <= bins; b++) {
      const cx = centers[b].x, cy = ys[b], cz = zs[b], r = rs[b];
      for (let k = 0; k <= seg; k++) {
        const a = (k / seg) * Math.PI * 2;
        const ny = Math.cos(a), nz = Math.sin(a);
        pos.push(cx, cy + r * ny, cz + r * nz);
        nor.push(0, ny, nz);
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
    g.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
    g.setIndex(idx);
    g.computeVertexNormals();
    const mat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
      uniforms: { uColor: { value: new THREE.Color("#2a6dff") }, uRim: { value: new THREE.Color("#7fe8ff") }, uTime: { value: 0 } },
      vertexShader: /* glsl */`
        varying vec3 vN; varying vec3 vV; varying float vX;
        void main(){
          vec4 mv = modelViewMatrix * vec4(position,1.0);
          vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); vX = position.x;
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */`
        uniform vec3 uColor; uniform vec3 uRim; uniform float uTime;
        varying vec3 vN; varying vec3 vV; varying float vX;
        void main(){
          float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.6);
          float band = 0.5 + 0.5*sin(vX*9.0 - uTime*0.8);
          vec3 c = mix(uColor, uRim, f) * (0.05 + 0.4*f) * (0.85 + 0.15*band);
          gl_FragColor = vec4(c, 0.16*f + 0.015);
        }`,
    });
    this.body = new THREE.Mesh(g, mat);
    this.scene.add(this.body);
  }

  _buildHighlightRings() {
    this.ringGroup = new THREE.Group();
    this.scene.add(this.ringGroup);
  }

  setHighlight(indices) {
    this.highlight = new Set(indices);
    this.ringGroup.clear();
    const geo = new THREE.RingGeometry(0.13, 0.16, 40);
    for (const i of indices) {
      const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
        color: "#ffd166", transparent: true, opacity: 0.85, side: THREE.DoubleSide, toneMapped: false,
        depthWrite: false,
      }));
      m.position.copy(this.positions[i]);
      m.userData.index = i;
      this.ringGroup.add(m);
    }
  }

  _buildLabel() {
    this.labelEl = document.createElement("div");
    Object.assign(this.labelEl.style, {
      position: "fixed", pointerEvents: "none", zIndex: 4, font: "600 12px var(--mono)", color: "#cfe9ff",
      textShadow: "0 0 8px rgba(56,225,255,.9)", transform: "translate(-50%, -160%)", whiteSpace: "nowrap",
    });
    document.body.appendChild(this.labelEl);
    this.labelIndex = -1;
  }

  setLabel(index, text) { this.labelIndex = index; this.labelEl.textContent = text ?? ""; }

  // ---------------------------------------------------------------- actividad
  setActivity(values) {
    this.activity = values;
    const n = this.neurons.length;
    const col = this.mesh.instanceColor.array;
    for (let i = 0; i < n; i++) {
      const v = values ? values[i] : 0;
      const base = this.baseColors[i];
      let s;
      if (v > 0.015) {
        colormap(v, this._tmpColor);
        const boost = 0.45 + 1.7 * v;
        this._tmpColor.multiplyScalar(boost);
        this._tmpColor.lerp(base, Math.max(0, 0.25 - v));
        s = 1 + 2.4 * Math.sqrt(v);
      } else {
        this._tmpColor.copy(base).multiplyScalar(0.33);
        s = 1;
      }
      if (this.highlight.has(i)) s *= 1.15;
      col[i * 3] = this._tmpColor.r; col[i * 3 + 1] = this._tmpColor.g; col[i * 3 + 2] = this._tmpColor.b;
      const p = this.positions[i];
      this._tmpMat.makeScale(s, s, s).setPosition(p.x, p.y, p.z);
      this.mesh.setMatrixAt(i, this._tmpMat);
    }
    this.mesh.instanceColor.needsUpdate = true;
    this.mesh.instanceMatrix.needsUpdate = true;

    // Sinapsis: brillan según la actividad de sus extremos
    const ec = this.edgeLines.geometry.attributes.color.array;
    this.edges.forEach(([i, j], k) => {
      const a = values ? values[i] : 0, b = values ? values[j] : 0;
      const act = Math.sqrt(a * b);
      const base = 0.25 + 0.75 * this.edgeW[k];
      colormap(0.45 + 0.55 * act, this._tmpColor);
      const k2 = act * (0.25 + 0.75 * this.edgeW[k]) * 0.55;
      const r = 0.025 * base + this._tmpColor.r * k2;
      const g = 0.04 * base + this._tmpColor.g * k2;
      const bl = 0.09 * base + this._tmpColor.b * k2;
      ec.set([r, g, bl, r, g, bl], k * 6);
    });
    this.edgeLines.geometry.attributes.color.needsUpdate = true;
  }

  setEdgesVisible(v) { this.edgeVisible = v; if (this.edgeLines) this.edgeLines.visible = v; }

  // ------------------------------------------------------------------- láser
  fireLaser(index, intensity = 1) {
    const target = this.positions[index];
    if (this.laser) this.scene.remove(this.laser.group);
    const group = new THREE.Group();
    const from = target.clone().add(new THREE.Vector3(-0.6, 4.5, 1.2));
    const dir = target.clone().sub(from);
    const len = dir.length();
    const mk = (r, color, op) => {
      const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r * 0.6, len, 16, 1, true),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: op, blending: THREE.AdditiveBlending,
          depthWrite: false, toneMapped: false }));
      m.position.copy(from).addScaledVector(dir, 0.5);
      m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize());
      return m;
    };
    const glow = mk(0.07, new THREE.Color("#4da3ff").multiplyScalar(1.6), 0.3);
    const core = mk(0.014, new THREE.Color("#e8f4ff").multiplyScalar(2), 0.9);
    group.add(glow, core);
    const flash = new THREE.Mesh(new THREE.SphereGeometry(0.3, 24, 16), new THREE.MeshBasicMaterial({
      color: new THREE.Color("#7cc4ff").multiplyScalar(3), transparent: true, opacity: 0.8,
      blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }));
    flash.position.copy(target);
    group.add(flash);
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.2, 0.24, 64), new THREE.MeshBasicMaterial({
      color: new THREE.Color("#4da3ff").multiplyScalar(2.5), transparent: true, opacity: 0.9,
      side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }));
    ring.position.copy(target);
    group.add(ring);
    this.scene.add(group);
    this.laser = { group, glow, core, flash, ring, t: 0, intensity };
  }

  _animateLaser(dt) {
    const L = this.laser;
    if (!L) return;
    L.t += dt;
    const on = Math.min(1, L.t / 0.15) * Math.max(0, 1 - Math.max(0, L.t - 0.9) / 0.6);
    const k = 0.35 + 0.65 * L.intensity;
    L.glow.material.opacity = 0.35 * on * k * (0.85 + 0.15 * Math.sin(L.t * 40));
    L.core.material.opacity = 0.95 * on * k;
    L.flash.material.opacity = 0.8 * on * k;
    L.flash.scale.setScalar(0.6 + 0.4 * Math.sin(Math.min(L.t, 1.2) * 6));
    const rr = 1 + L.t * 5;
    L.ring.scale.setScalar(rr);
    L.ring.material.opacity = Math.max(0, 0.9 - L.t * 0.7);
    L.ring.lookAt(this.camera.position);
    if (L.t > 1.6) { this.scene.remove(L.group); this.laser = null; }
  }

  focus(index) {
    const p = this.positions[index];
    this._focusTarget = p.clone();
  }

  // ---------------------------------------------------------------- interno
  _addStars() {
    const n = 1400;
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
    window.addEventListener("resize", () => this._resize());
    this.canvas.addEventListener("pointermove", (e) => {
      this.pointer.set((e.clientX / window.innerWidth) * 2 - 1, -(e.clientY / window.innerHeight) * 2 + 1);
      this._pointerPx = [e.clientX, e.clientY];
    });
    this.canvas.addEventListener("pointerleave", () => { this.pointer.set(2, 2); });
    let down = null;
    this.canvas.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY]; this.controls.autoRotate = false; });
    this.canvas.addEventListener("pointerup", (e) => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
      if (this.hovered >= 0) this.callbacks.pick(this.hovered);
    });
  }

  _resize() {
    const w = window.innerWidth, h = window.innerHeight;
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    this.bloom.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  _tick() {
    const dt = Math.min(0.05, this.clock.getDelta());
    if (this._focusTarget) {
      this.controls.target.lerp(this._focusTarget, 0.06);
      if (this.controls.target.distanceTo(this._focusTarget) < 0.01) this._focusTarget = null;
    }
    this.controls.update();
    if (this.body) this.body.material.uniforms.uTime.value += dt;
    this._animateLaser(dt);
    if (this.ringGroup) this.ringGroup.children.forEach((m) => m.lookAt(this.camera.position));

    // hover
    if (this.pickMesh) {
      this.raycaster.setFromCamera(this.pointer, this.camera);
      const hit = this.raycaster.intersectObject(this.pickMesh, false)[0];
      const idx = hit ? hit.instanceId : -1;
      if (idx !== this.hovered) {
        this.hovered = idx;
        this.canvas.style.cursor = idx >= 0 ? "pointer" : "grab";
      }
      this.callbacks.hover(idx, this._pointerPx);
    }
    // etiqueta
    if (this.labelIndex >= 0 && this.positions) {
      const p = this._tmpVec.copy(this.positions[this.labelIndex]).project(this.camera);
      const visible = p.z < 1;
      this.labelEl.style.display = visible ? "block" : "none";
      this.labelEl.style.left = `${(p.x * 0.5 + 0.5) * window.innerWidth}px`;
      this.labelEl.style.top = `${(-p.y * 0.5 + 0.5) * window.innerHeight}px`;
    }
    this.composer.render(dt);
  }
}
