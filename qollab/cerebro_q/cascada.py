"""Cascada cuántica de spikes: quantum walk por ventanas (docs/PLAN_WALK_VENTANAS.md).

Cada paso:
    1. ventana = neurona central + sus 9 vecinas con más sinapsis (10 qubits);
    2. circuito Qiskit: X (o RX(θ) en el primer paso) en el centro y evolución XY durante τ,
       e^{-iτH},  H = γ Σ J_ij (X_i X_j + Y_i Y_j)/2  restringido a la ventana;
    3. un job en el backend elegido, medición de los 10 qubits;
    4. el spike = la neurona en 1 de un shot válido (exactamente un 1) elegido al azar;
       esa neurona es el centro del paso siguiente.

Al medir, el estado colapsa: la interferencia vive dentro de cada paso, no entre pasos.
`comparacion_json` contrasta el walk coherente, el medido cada τ y la caminata clásica.
"""

from __future__ import annotations

import random
from functools import lru_cache

import numpy as np

from . import analisis, circuitos, datos, fisica

TAMANO_VENTANA = 10


# ---------------------------------------------------------------------------
# Ventana
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def conteo_sinapsis() -> np.ndarray:
    """Número de sinapsis entre cada par (química en ambos sentidos + gap). Simétrica."""
    _, nombres, _ = fisica.acoplamientos()
    idx = {n: i for i, n in enumerate(nombres)}
    c = np.zeros((len(nombres), len(nombres)))
    for a, b, w, _tipo in datos.sinapsis():
        if a in idx and b in idx and a != b:
            c[idx[a], idx[b]] += w
    return c + c.T


def ventana(centro: int, k: int = TAMANO_VENTANA) -> list[int]:
    """[centro] + vecinas directas ordenadas por número de sinapsis; si faltan, a 2 sinapsis.

    Con pesos binarios todas las conexiones valen lo mismo en J, así que el orden usa el
    número de sinapsis de los datos (desempate por índice, para que sea determinista).
    """
    J, _, _ = fisica.acoplamientos()
    cnt = conteo_sinapsis()
    vecinas = [int(j) for j in np.nonzero(J[centro])[0]]
    vecinas.sort(key=lambda j: (-cnt[centro, j], j))
    elegidas = vecinas[: k - 1]
    if len(elegidas) < k - 1:  # completar con neuronas a distancia 2
        candidatas: dict[int, float] = {}
        for v in elegidas:
            for j in np.nonzero(J[v])[0]:
                j = int(j)
                if j != centro and j not in elegidas:
                    candidatas[j] = candidatas.get(j, 0.0) + cnt[v, j]
        extra = sorted(candidatas, key=lambda j: (-candidatas[j], j))
        elegidas += extra[: k - 1 - len(elegidas)]
    return [int(centro)] + elegidas


# ---------------------------------------------------------------------------
# Circuito de un paso
# ---------------------------------------------------------------------------
def operaciones_paso(Js: np.ndarray, theta: float, tau: float, gamma: float, pasos: int) -> list[tuple]:
    """Lista de operaciones (control numpy): láser en el qubit 0 + Trotter-Suzuki de 2º orden."""
    return circuitos.operaciones(len(Js), [0], theta, circuitos.saltos_trotter(Js, tau, pasos, gamma, 2))


def circuito_paso(Js: np.ndarray, theta: float, tau: float, gamma: float, pasos: int, nombre: str = "paso"):
    """Circuito Qiskit del paso. Usa PauliEvolutionGate + SuzukiTrotter (simulación hamiltoniana
    nativa de Qiskit); si esa API no existe (pruebas sin Qiskit real), usa RXX/RYY equivalentes.

    Devuelve (circuito, "pauli_evolution" | "rxx_ryy").
    """
    n = len(Js)
    try:
        from qiskit import QuantumCircuit
        from qiskit.circuit.library import PauliEvolutionGate
        from qiskit.quantum_info import SparsePauliOp
        from qiskit.synthesis import SuzukiTrotter
    except ImportError:
        ops = operaciones_paso(Js, theta, tau, gamma, pasos)
        return circuitos.a_qiskit(ops, n, nombre=nombre, medir=True), "rxx_ryy"

    terminos = []
    for a, b, w in circuitos.aristas(Js):
        c = gamma * w / 2.0  # H = γ Σ J (XX + YY)/2
        terminos += [("XX", [a, b], c), ("YY", [a, b], c)]
    qc = QuantumCircuit(n, n, name=nombre)
    if abs(theta - np.pi) < 1e-12:
        qc.x(0)  # spike medido: la neurona central está excitada con certeza
    else:
        qc.rx(theta, 0)
    if terminos and tau > 0:
        H = SparsePauliOp.from_sparse_list(terminos, num_qubits=n)
        evol = PauliEvolutionGate(H, time=tau, synthesis=SuzukiTrotter(order=2, reps=pasos),
                                  label=rf"$e^{{-i\tau H_{{XY}}}}$  τ={tau:g}")
        qc.append(evol, range(n))
    qc.measure(range(n), range(n))
    return qc, "pauli_evolution"


def _ops(circ) -> dict:
    try:
        return {str(k): int(v) for k, v in circ.count_ops().items()}
    except Exception:
        return {}


def ejecutar_paso(backend, centro: int, theta: float, tau: float, gamma: float, shots: int,
                  pasos: int = 1, semilla: int | None = None) -> dict:
    """Un paso de la cascada: UN job en el backend. Devuelve todo lo que dibuja la página."""
    _, nombres, _ = fisica.acoplamientos()
    w = ventana(centro)
    J, _, _ = fisica.acoplamientos()
    Js = J[np.ix_(w, w)]
    n = len(w)
    qc, metodo = circuito_paso(Js, theta, tau, gamma, pasos, nombre=f"paso-{nombres[centro]}")
    try:
        from qiskit import transpile

        enviar = transpile(qc, backend, optimization_level=1)
    except Exception:
        enviar = qc
    resultado = backend.run(enviar, shots=int(shots)).result()
    conteos = resultado.get_counts()
    if isinstance(conteos, list):
        conteos = conteos[0]
    medida = analisis.conteos_a_probs(conteos, n)

    # Shots válidos = como mucho una excitación (la dinámica no crea excitaciones: los demás son
    # errores y se descartan, post-selección). Con una excitación, el bit en 1 es el spike; sin
    # excitación ("vacío") la neurona no disparó: pasa si θ < π en el primer paso, o por ruido.
    peso = analisis.peso_hamming(np.arange(1 << n))
    validos: dict[int, int] = {}
    vacios = 0
    for clave, v in conteos.items():
        x = int(str(clave).replace(" ", ""), 2)
        if peso[x] == 1:
            q = x.bit_length() - 1
            validos[q] = validos.get(q, 0) + int(v)
        elif peso[x] == 0:
            vacios += int(v)
    total_validos = sum(validos.values())
    total = sum(int(v) for v in conteos.values()) or 1

    spike, motivo_fin = None, None
    if total_validos + vacios:
        rng = random.Random(semilla)
        r = rng.randrange(total_validos + vacios)  # un shot post-seleccionado al azar
        for q in sorted(validos):
            r -= validos[q]
            if r < 0:
                spike = q
                break
        if spike is None:
            motivo_fin = "vacio"
    else:
        motivo_fin = "sin_shots_validos"

    # Teoría para comparar: walk exacto en la ventana aislada y cuánto se escaparía en la red real
    ideal = circuitos.probabilidades_ideales(operaciones_paso(Js, theta, tau, gamma, max(pasos, 1)), n)
    exacta_ventana = fisica.probabilidades_walk(np.linalg.eigh(Js), 0, np.array([tau]), theta, gamma)[0]
    red = fisica.probabilidades_walk(fisica.diagonalizacion(), centro, np.array([tau]), theta, gamma)[0]
    return {
        "centro": nombres[centro],
        "ventana": [nombres[i] for i in w],
        "ventana_indices": w,
        "medida": [validos.get(q, 0) / max(total_validos, 1) for q in range(n)],  # P(spike en q | hubo spike)
        "medida_bruta": analisis.marginales(medida, n),
        "teoria_ventana": exacta_ventana / max(exacta_ventana.sum(), 1e-12),
        "teoria_circuito": analisis.marginales(ideal, n),
        "fuga_red": float(1 - red[w].sum() / max(red.sum(), 1e-12)),
        "fraccion_valida": (total_validos + vacios) / total,
        "fraccion_vacio": vacios / total,
        "motivo_fin": motivo_fin,
        "spike": nombres[w[spike]] if spike is not None else None,
        "spike_indice": int(w[spike]) if spike is not None else None,
        "shots": int(total),
        "metodo": metodo,
        "ops_escritas": _ops(qc),
        "ops_transpilado": _ops(enviar),
        "conteos": {str(k): int(v) for k, v in conteos.items()},
    }


# ---------------------------------------------------------------------------
# Comparación: coherente vs medido cada τ vs clásico (todo exacto, numpy)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def distancias() -> np.ndarray:
    """Distancia en sinapsis entre todos los pares (BFS sobre el grafo)."""
    J, _, _ = fisica.acoplamientos()
    n = len(J)
    vecinos = [np.nonzero(J[i])[0] for i in range(n)]
    D = np.full((n, n), np.inf)
    for s in range(n):
        D[s, s] = 0
        frente = [s]
        while frente:
            nuevo = []
            for u in frente:
                for v in vecinos[u]:
                    if D[s, v] == np.inf:
                        D[s, v] = D[s, u] + 1
                        nuevo.append(v)
            frente = nuevo
    return D


def comparacion(centro: int, tau: float, pasos: int, gamma: float = 1.0, trayectorias: int = 300,
                semilla: int = 7) -> dict:
    """Probabilidad de seguir en el origen y distancia media al origen (en sinapsis), en los
    tiempos t = kτ, para:
      coherente  : walk cuántico sin medir (exacto, red completa);
      medido     : walk medido cada τ en la red completa = cadena de Markov exacta
                   con T_ij = |[e^{-iγJτ}]_ij|^2 (límite de ventana infinita);
      ventanas   : la cascada de 10 qubits (simulada con numpy, `trayectorias` corridas);
      clasico    : caminata aleatoria clásica dp/dt = -γ L p.
    """
    J, _, _ = fisica.acoplamientos()
    lam, V = fisica.diagonalizacion()
    D = distancias()
    d = np.where(np.isfinite(D[centro]), D[centro], 0.0)
    tiempos = tau * np.arange(pasos + 1)

    coh = fisica.probabilidades_walk((lam, V), centro, tiempos, np.pi, gamma)
    U = (V * np.exp(-1j * gamma * lam * tau)) @ V.T
    T = np.abs(U) ** 2  # T[k, j] = P(j → k) en un paso medido
    med = [np.eye(len(J))[centro]]
    for _ in range(pasos):
        med.append(T @ med[-1])
    med = np.array(med)
    L = np.diag(J.sum(1)) - J
    mu, W = np.linalg.eigh(L)
    cla = np.array([(W * np.exp(-gamma * mu * t)) @ W[centro] for t in tiempos])

    rng = np.random.default_rng(semilla)
    cache: dict[int, tuple[list[int], np.ndarray]] = {}
    ocupacion = np.zeros((pasos + 1, len(J)))
    for _ in range(trayectorias):
        c = centro
        ocupacion[0, c] += 1
        for k in range(1, pasos + 1):
            if c not in cache:
                w = ventana(c)
                Js = J[np.ix_(w, w)]
                p = fisica.probabilidades_walk(np.linalg.eigh(Js), 0, np.array([tau]), np.pi, gamma)[0]
                cache[c] = (w, p / p.sum())
            w, p = cache[c]
            c = w[int(rng.choice(len(w), p=p))]
            ocupacion[k, c] += 1
    ven = ocupacion / trayectorias

    def resumen(P):
        P = P / np.maximum(P.sum(axis=1, keepdims=True), 1e-15)
        return {"origen": P[:, centro], "distancia": P @ d}

    return {
        "tiempos": tiempos,
        "tau": tau,
        "curvas": {
            "coherente": resumen(coh),
            "medido": resumen(med),
            "ventanas": resumen(ven),
            "clasico": resumen(cla),
        },
    }
