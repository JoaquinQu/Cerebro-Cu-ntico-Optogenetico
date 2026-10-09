// Cliente de la API del backend (misma origen: http://127.0.0.1:8000)
const BASE = window.CEREBRO_API ?? "";

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let data;
  try { data = await res.json(); } catch { data = {}; }
  if (!res.ok) {
    const msg = data?.error ?? `Error ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

export const api = {
  health: () => request("/api/health"),
  connectome: () => request("/api/connectome?max_edges=1200"),
  walk: (body) => request("/api/walk", { method: "POST", body: JSON.stringify(body) }),
  microcircuits: () => request("/api/microcircuits"),
  simulate: (body) => request("/api/microcircuit/simulate", { method: "POST", body: JSON.stringify(body) }),
  submit: (body) => request("/api/ionq/submit", { method: "POST", body: JSON.stringify(body) }),
  jobs: () => request("/api/ionq/jobs"),
  job: (id) => request(`/api/ionq/jobs/${encodeURIComponent(id)}`),
};
