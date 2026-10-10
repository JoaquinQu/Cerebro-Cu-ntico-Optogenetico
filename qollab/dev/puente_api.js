// SÓLO PARA DESARROLLO LOCAL (no se sube a Qollab).
// Imita el módulo Python `cerebro_q.api` que Qollab expone a JavaScript: cada función
// tiene .callPromising(...) y aquí se resuelve con un POST al servidor de dev/servidor.py.
const BACKEND_TOKEN = "__backend__";

async function call(nombre, args) {
  const cuerpo = args.map((a) => (a === globalThis.backend ? BACKEND_TOKEN : a));
  const r = await fetch(`/api/${nombre}${location.search}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo),
  });
  const texto = await r.text();
  if (!r.ok) throw new Error(texto || `HTTP ${r.status}`);
  return texto; // igual que en Qollab: la función Python devuelve un str
}

const fn = (nombre) => ({ callPromising: (...args) => call(nombre, args) });

export const conectoma_json = fn("conectoma_json");
export const walk_json = fn("walk_json");
export const cuerpo_glb = fn("cuerpo_glb");
export const microcircuitos_json = fn("microcircuitos_json");
export const simular_json = fn("simular_json");
export const backend_json = fn("backend_json");
export const ejecutar_json = fn("ejecutar_json");
export const paso_json = fn("paso_json");
export const comparacion_json = fn("comparacion_json");
export const figuras_json = fn("figuras_json");
