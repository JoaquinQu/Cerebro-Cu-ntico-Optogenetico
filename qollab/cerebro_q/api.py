"""Funciones que llama main.js (con .callPromising). Todas devuelven texto JSON.

Devolver JSON evita depender de la conversión de proxies de Pyodide (dict → Map):
en JavaScript basta con JSON.parse(resultado).
"""

from __future__ import annotations

import json
import math

import numpy as np

from . import analisis, cascada, circuitos, datos, fisica
from .microcircuitos import MICROCIRCUITOS


def _json(obj) -> str:
    def limpiar(o):
        if isinstance(o, dict):
            return {str(k): limpiar(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [limpiar(v) for v in o]
        if isinstance(o, np.ndarray):
            return limpiar(o.tolist())
        if isinstance(o, (np.floating, float)):
            v = float(o)
            return None if math.isnan(v) or math.isinf(v) else round(v, 6)
        if isinstance(o, np.integer):
            return int(o)
        return o

    return json.dumps(limpiar(obj), ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Red completa
# ---------------------------------------------------------------------------
def conectoma_json(max_aristas: int = 1200) -> str:
    J, nombres, escala = fisica.acoplamientos()
    neu = datos.neuronas()
    grado = (J > 0).sum(axis=1)
    iu, ju = np.triu_indices(len(J), 1)
    w = J[iu, ju]
    orden = np.argsort(-w)[: int(max_aristas)]
    orden = orden[w[orden] > 0]
    return _json({
        "neurons": [{"name": d["name"], "x": d["x"], "y": d["y"], "z": d["z"], "type": d["type"],
                     "neurotransmitters": d.get("neurotransmitters", []), "degree": int(g)}
                    for d, g in zip(neu, grado)],
        "edges": [[int(iu[k]), int(ju[k]), float(w[k])] for k in orden],
        "spectral_scale": escala,
    })


def walk_json(fuente: str = "AVM", theta: float = math.pi, gamma: float = 1.0, t_max: float = 60.0,
              cuadros: int = 160) -> str:
    j = fisica.indice(fuente)
    tiempos = np.linspace(0.0, float(t_max), int(cuadros))
    P = fisica.probabilidades_walk(fisica.diagonalizacion(), j, tiempos, float(theta), float(gamma))
    q = P / np.maximum(P.sum(axis=1, keepdims=True), 1e-15)
    return _json({
        "source": fisica.acoplamientos()[1][j],
        "fire_probability": math.sin(theta / 2) ** 2,
        "times": tiempos,
        "prob": np.round(P, 5),
        "participation": 1.0 / np.sum(q**2, axis=1),
    })


def cuerpo_glb() -> str:
    """Modelo 3D en base64 ("" si falta: la página dibuja entonces un cuerpo procedural)."""
    try:
        return datos.cuerpo_glb_base64()
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Microcircuito
# ---------------------------------------------------------------------------
def microcircuitos_json() -> str:
    out = []
    for clave, m in MICROCIRCUITOS.items():
        J = fisica.sub_acoplamientos(m["neuronas"])
        out.append({"id": clave, **m, "conexiones": int((np.triu(J, 1) > 0).sum())})
    return _json({"microcircuitos": out})


def _preparar(p: dict):
    m = MICROCIRCUITOS[p.get("preset", "toque-6")]
    nombres = m["neuronas"]
    fuente = datos.normalizar_nombre(p.get("fuente") or m["fuente"])
    if fuente not in nombres:
        fuente = m["fuente"]
    J = fisica.sub_acoplamientos(nombres)
    return nombres, J, [nombres.index(fuente)], fuente


def _saltos(J, fuentes, theta, t, gamma, modo, pasos, orden):
    if modo == "givens":
        lam, V = np.linalg.eigh(J)
        amp = V @ (np.exp(-1j * gamma * lam * t) * V[fuentes[0]])
        return circuitos.saltos_givens(amp, fuentes[0])
    return circuitos.saltos_trotter(J, t, pasos, gamma, orden)


def _autoajuste(J, fuentes, theta, t, gamma, orden, max_pasos):
    n = len(J)
    exacta = fisica.distribucion_exacta(J, fuentes, theta, t, gamma)
    tabla = []
    for r in range(1, max_pasos + 1):
        ops = circuitos.operaciones(n, fuentes, theta, circuitos.saltos_trotter(J, t, r, gamma, orden))
        rec = circuitos.recursos(ops)
        e = analisis.tvd(exacta, circuitos.probabilidades_ideales(ops, n))
        tabla.append({"pasos": r, "tvd_trotter": e, "fidelidad": rec["fidelidad_estimada"],
                      "compuertas_2q": rec["compuertas_2q"], "error_total": e + 1 - rec["fidelidad_estimada"]})
    return min(tabla, key=lambda f: f["error_total"])["pasos"], tabla


def simular_json(params_json: str) -> str:
    """Teoría exacta vs. circuito ideal vs. ruido tipo Forte, sin usar el backend (instantáneo)."""
    p = json.loads(params_json or "{}")
    nombres, J, fuentes, fuente = _preparar(p)
    n = len(nombres)
    theta, t, gamma = float(p.get("theta", math.pi)), float(p.get("t", 30)), float(p.get("gamma", 1))
    modo, orden = p.get("modo", "trotter"), int(p.get("orden", 2))
    pasos = int(p.get("pasos") or 0)
    tabla = None
    if modo == "trotter" and pasos <= 0:
        pasos, tabla = _autoajuste(J, fuentes, theta, t, gamma, orden, 6 if n <= 7 else 3)
    pasos = max(pasos, 1)
    saltos = _saltos(J, fuentes, theta, t, gamma, modo, pasos, orden)
    ops = circuitos.operaciones(n, fuentes, theta, saltos)
    exacta = fisica.distribucion_exacta(J, fuentes, theta, t, gamma)
    ideal = circuitos.probabilidades_ideales(ops, n)
    out = {
        "neuronas": nombres, "fuente": fuente, "n_qubits": n, "theta": theta, "t": t, "gamma": gamma,
        "modo": modo, "pasos": pasos, "orden": orden,
        "exacta": analisis.marginales(exacta, n),
        "ideal": analisis.marginales(ideal, n),
        "tvd_circuito": analisis.tvd(exacta, ideal),
        "recursos": circuitos.recursos(ops),
        "autoajuste": tabla,
        "saltos": [{"a": a, "b": b, "alfa": al, "tag": tag} for a, b, al, tag in saltos],
    }
    if n <= 10:
        ruido = circuitos.probabilidades_con_ruido(ops, n, trayectorias=150 if n <= 7 else 60)
        out["ruido"] = analisis.comparar(exacta, ruido, n, len(fuentes))
    ts = np.linspace(0, max(t * 1.5, 1.0), 61)
    out["serie"] = {"tiempos": ts,
                    "marginales": fisica.probabilidades_walk(np.linalg.eigh(J), fuentes[0], ts, theta, gamma)}
    try:  # dibujo del circuito Qiskit en texto (accesible para lectores de pantalla)
        qc = circuitos.a_qiskit(ops, n, medir=True)
        out["qiskit_texto"] = str(qc.draw(output="text", fold=-1))[:20000]
        out["qiskit_ops"] = {k: int(v) for k, v in qc.count_ops().items()}
    except ImportError:
        out["qiskit_texto"] = None
    return _json(out)


def _nombre_backend(backend) -> str:
    nombre = getattr(backend, "name", None)
    if callable(nombre):
        nombre = nombre()
    return str(nombre or backend)


def backend_json(backend) -> str:
    """Nombre del backend elegido en Qollab y si es de IonQ (un solo job por ejecución)."""
    nombre = _nombre_backend(backend)
    origen = f"{nombre} {type(backend).__module__} {type(backend).__name__}".lower()
    ionq = "ionq" in origen
    try:
        qubits = int(getattr(backend, "num_qubits", 0) or 0)
    except Exception:
        qubits = 0
    return _json({"nombre": nombre, "ionq": ionq, "hardware": ionq and "qpu" in nombre.lower(),
                  "qubits": qubits})


def ejecutar_json(backend, params_json: str) -> str:
    """Corre el microcircuito en el backend elegido en Qollab (UN solo job, varios tiempos).

    IonQ acepta un job por ejecución, así que todos los circuitos (uno por cada t)
    van juntos en una sola llamada a backend.run.
    """
    p = json.loads(params_json or "{}")
    nombres, J, fuentes, fuente = _preparar(p)
    n = len(nombres)
    theta, gamma = float(p.get("theta", math.pi)), float(p.get("gamma", 1))
    modo, orden = p.get("modo", "trotter"), int(p.get("orden", 2))
    pasos = max(int(p.get("pasos") or 2), 1)  # mismos pasos para todos los t (buena práctica de IonQ)
    tiempos = [float(x) for x in (p.get("tiempos") or [p.get("t", 30)])]
    shots = int(p.get("shots", 500))

    circuitos_q, exactas = [], []
    for t in tiempos:
        ops = circuitos.operaciones(n, fuentes, theta, _saltos(J, fuentes, theta, t, gamma, modo, pasos, orden))
        circuitos_q.append(circuitos.a_qiskit(ops, n, nombre=f"t={t:g}"))
        exactas.append(fisica.distribucion_exacta(J, fuentes, theta, t, gamma))

    # Transpilar con optimization_level=1 (lo que recomienda qiskit-ionq). En IonQ deja RXX/RYY
    # tal cual (IonQ compila en su servidor); en los simuladores con ruido de IBM los reescribe
    # a sus compuertas nativas y agrega SWAPs por la topología: así se ve el costo de no tener
    # conectividad total.
    try:
        from qiskit import transpile

        enviar = transpile(circuitos_q, backend, optimization_level=1)
    except Exception:  # sin transpile disponible (p. ej. pruebas locales): se envía tal cual
        enviar = circuitos_q
    ops_transpilado = {}
    try:
        ops_transpilado = {str(k): int(v) for k, v in enviar[0].count_ops().items()}
    except Exception:
        pass

    job = backend.run(enviar if len(enviar) > 1 else enviar[0], shots=shots)
    resultado = job.result()
    filas = []
    for i, t in enumerate(tiempos):
        conteos = resultado.get_counts(i) if len(circuitos_q) > 1 else resultado.get_counts()
        medida = analisis.conteos_a_probs(conteos, n)
        filas.append({"t": t, "exacta": analisis.marginales(exactas[i], n),
                      **analisis.comparar(exactas[i], medida, n, len(fuentes)),
                      "conteos": {str(k): int(v) for k, v in conteos.items()}})
    job_id = getattr(job, "job_id", None)
    return _json({
        "backend": _nombre_backend(backend), "job_id": job_id() if callable(job_id) else job_id,
        "neuronas": nombres, "fuente": fuente, "shots": shots, "pasos": pasos, "modo": modo,
        "ops_escritas": {str(k): int(v) for k, v in circuitos_q[0].count_ops().items()},
        "ops_transpilado": ops_transpilado,
        "resultados": filas,
    })


# ---------------------------------------------------------------------------
# Cascada cuántica de spikes (quantum walk por ventanas)
# ---------------------------------------------------------------------------
def paso_json(backend, params_json: str) -> str:
    """Un paso de la cascada = UN circuito de 10 qubits en UN job del backend elegido."""
    p = json.loads(params_json or "{}")
    centro = fisica.indice(p.get("centro", "AVM"))
    out = cascada.ejecutar_paso(
        backend, centro,
        theta=float(p.get("theta", math.pi)), tau=float(p.get("tau", 8.0)), gamma=float(p.get("gamma", 1.0)),
        shots=int(p.get("shots", 200)), pasos=int(p.get("pasos_trotter", 1)),
        semilla=p.get("semilla"),
    )
    out["backend"] = _nombre_backend(backend)
    return _json(out)


def comparacion_json(params_json: str) -> str:
    """Coherente vs medido cada τ vs cascada por ventanas vs clásico (numpy, sin backend)."""
    p = json.loads(params_json or "{}")
    centro = fisica.indice(p.get("centro", "AVM"))
    return _json(cascada.comparacion(centro, tau=float(p.get("tau", 8.0)), pasos=int(p.get("pasos", 20)),
                                     gamma=float(p.get("gamma", 1.0)),
                                     trayectorias=int(p.get("trayectorias", 300))))
