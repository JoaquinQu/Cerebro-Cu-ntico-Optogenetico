// Puente con el núcleo Python (cerebro_q/api.py), que corre en Pyodide dentro de Qollab.
//
// Reglas de Qollab que se respetan aquí:
//   * las funciones Python se llaman con .callPromising (en backends de IonQ una llamada
//     directa falla con "XHR is not supported");
//   * cada función devuelve texto JSON, así no dependemos de cómo Pyodide convierte dict/list.
import * as api from "cerebro_q.api";

const texto = (r) => {
  if (typeof r === "string") return r;
  try { return r.toString(); } finally { r?.destroy?.(); }
};

/** Deja que el navegador pinte (p. ej. "Calculando…") antes de un cálculo largo en Python. */
export const respirar = () => new Promise((ok) => requestAnimationFrame(() => setTimeout(ok, 0)));

async function llamar(nombre, ...args) {
  const fn = api[nombre];
  if (!fn) throw new Error(`cerebro_q.api.${nombre} no existe`);
  return JSON.parse(texto(await fn.callPromising(...args)));
}

export const py = {
  conectoma: (maxAristas = 1200) => llamar("conectoma_json", maxAristas),
  walk: ({ fuente, theta, gamma, t_max, cuadros = 160 }) => llamar("walk_json", fuente, theta, gamma, t_max, cuadros),
  microcircuitos: () => llamar("microcircuitos_json"),
  simular: (params) => llamar("simular_json", JSON.stringify(params)),
  backendInfo: (backend) => llamar("backend_json", backend),
  ejecutar: (backend, params) => llamar("ejecutar_json", backend, JSON.stringify(params)),
  /** Bytes del cuerpo 3D (data/gusano.glb): Python lo lee y lo entrega en base64. */
  async cuerpo() {
    const b64 = texto(await api.cuerpo_glb.callPromising());
    if (!b64) return null;
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out.buffer;
  },
};
