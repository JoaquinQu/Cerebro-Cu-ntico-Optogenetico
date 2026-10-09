"""Circuitos del microcircuito: lista de operaciones → Qiskit, más un simulador numpy de control.

Operaciones (todas compuertas estándar de Qiskit):
    ("rx",  q,    θ)   láser optogenético            RX(θ)  = exp(-iθX/2)
    ("rxx", a, b, α)   mitad XX de un salto           RXX(α) = exp(-iα XX/2)
    ("ryy", a, b, α)   mitad YY de un salto           RYY(α) = exp(-iα YY/2)

Un salto de excitación entre las neuronas a y b durante δt es
    exp(-i γ J_ab δt (XX+YY)/2) = RXX(α)·RYY(α),   α = γ J_ab δt   (XX y YY conmutan).

En IonQ Forte cada RXX/RYY se compila a una compuerta ZZ nativa más rotaciones de un
qubit (la conectividad es total: no hay SWAPs). En los simuladores con ruido de IBM
el transpilador agrega SWAPs por la topología de vecinos cercanos.
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Construcción de la lista de operaciones
# ---------------------------------------------------------------------------


def aristas(J: np.ndarray, peso_min: float = 0.0) -> list[tuple[int, int, float]]:
    n = len(J)
    return [(i, j, float(J[i, j])) for i in range(n) for j in range(i + 1, n) if J[i, j] > peso_min]


def _fusionar(saltos: list[tuple[int, int, float, str]]) -> list[tuple[int, int, float, str]]:
    out: list[tuple[int, int, float, str]] = []
    for a, b, ang, tag in saltos:
        if out and {out[-1][0], out[-1][1]} == {a, b}:
            pa, pb, pang, ptag = out.pop()
            out.append((pa, pb, pang + ang, ptag))
        else:
            out.append((a, b, ang, tag))
    return out


def saltos_trotter(J: np.ndarray, t: float, pasos: int, gamma: float = 1.0, orden: int = 2):
    """Saltos (a, b, α) de la fórmula de Trotter–Suzuki de 1er o 2º orden (Strang)."""
    E = aristas(J)
    if t == 0 or not E:
        return []
    dt = t / pasos
    saltos = []
    for s in range(pasos):
        tag = f"trotter-{s + 1}"
        if orden == 1:
            saltos += [(i, j, gamma * w * dt, tag) for i, j, w in E]
        else:
            saltos += [(i, j, gamma * w * dt / 2, tag) for i, j, w in E]
            saltos += [(i, j, gamma * w * dt / 2, tag) for i, j, w in reversed(E)]
    return _fusionar(saltos)


def saltos_givens(amplitudes: np.ndarray, fuente: int):
    """Cascada de n−1 saltos que reproduce exactamente |v_k| desde |e_fuente⟩ (TEORIA §6.3)."""
    v = np.abs(amplitudes)
    v = v / np.linalg.norm(v)
    orden = [fuente] + [int(k) for k in np.argsort(-v) if k != fuente]
    R, out = 1.0, []
    for m in range(len(v) - 1):
        a, b = orden[m], orden[m + 1]
        if R < 1e-12:
            break
        alfa = float(np.arccos(np.clip(v[a] / R, 0.0, 1.0)))
        if alfa > 1e-9:
            out.append((a, b, alfa, f"givens-{m + 1}"))
        R *= np.sin(alfa)
    return out


def operaciones(n: int, fuentes: list[int], theta: float, saltos) -> list[tuple]:
    ops: list[tuple] = [("rx", q, theta) for q in fuentes]
    for a, b, alfa, _tag in saltos:
        ops += [("rxx", a, b, alfa), ("ryy", a, b, alfa)]
    return ops


# ---------------------------------------------------------------------------
# Qiskit
# ---------------------------------------------------------------------------


def a_qiskit(ops: list[tuple], n: int, nombre: str = "microcircuito", medir: bool = True):
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(n, n if medir else 0, name=nombre)
    for op in ops:
        if op[0] == "rx":
            qc.rx(op[2], op[1])
        elif op[0] == "rxx":
            qc.rxx(op[3], op[1], op[2])
        elif op[0] == "ryy":
            qc.ryy(op[3], op[1], op[2])
    if medir:
        qc.measure(list(range(n)), list(range(n)))
    return qc


# ---------------------------------------------------------------------------
# Simulador numpy de control (mismas convenciones que Qiskit: qubit 0 = bit menos significativo)
# ---------------------------------------------------------------------------
_I = np.eye(2, dtype=complex)
_X = np.array([[0, 1], [1, 0]], dtype=complex)
_Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
_Z = np.array([[1, 0], [0, -1]], dtype=complex)
_PAULIS = [_I, _X, _Y, _Z]


def _matriz(op) -> np.ndarray:
    if op[0] == "rx":
        a = op[2] / 2
        return np.cos(a) * _I - 1j * np.sin(a) * _X
    a = op[3] / 2
    P = np.kron(_X, _X) if op[0] == "rxx" else np.kron(_Y, _Y)
    return np.cos(a) * np.eye(4) - 1j * np.sin(a) * P


def _aplicar_1q(psi, U, q):
    t = psi.reshape(-1, 2, 1 << q)
    return np.einsum("ij,ajb->aib", U, t).reshape(-1)


def _aplicar_2q(psi, n, U, a, b):
    hi, lo = (a, b) if a > b else (b, a)
    t = psi.reshape(1 << (n - 1 - hi), 2, 1 << (hi - 1 - lo), 2, 1 << lo)
    U4 = U.reshape(2, 2, 2, 2)
    out = np.einsum("xyuv,AuMvL->AxMyL", U4, t) if a > b else np.einsum("xyuv,AvMuL->AyMxL", U4, t)
    return out.reshape(-1)


def _aplicar(psi, n, op, U):
    return _aplicar_1q(psi, U, op[1]) if op[0] == "rx" else _aplicar_2q(psi, n, U, op[1], op[2])


def probabilidades_ideales(ops: list[tuple], n: int) -> np.ndarray:
    psi = np.zeros(1 << n, dtype=complex)
    psi[0] = 1.0
    for op in ops:
        psi = _aplicar(psi, n, op, _matriz(op))
    return np.abs(psi) ** 2


def probabilidades_con_ruido(ops, n, f1q=0.9998, f2q=0.996, lectura=0.005, trayectorias=200, semilla=7):
    """Ruido despolarizante tipo IonQ Forte (estimador estratificado, TEORIA §7)."""
    rng = np.random.default_rng(semilla)
    mats = [_matriz(op) for op in ops]
    p = np.array([(1 - f2q) if op[0] != "rx" else (1 - f1q) for op in ops])
    psi = np.zeros(1 << n, dtype=complex)
    psi[0] = 1.0
    prefijo = [psi]
    for op, U in zip(ops, mats):
        psi = _aplicar(psi, n, op, U)
        prefijo.append(psi)
    ideal = np.abs(prefijo[-1]) ** 2
    sobrevive = np.concatenate([[1.0], np.cumprod(1 - p)])
    P0 = sobrevive[-1]
    primero = p * sobrevive[:-1]
    if trayectorias <= 0 or primero.sum() <= 0:
        return _error_lectura(ideal, n, lectura)
    primero = primero / primero.sum()
    acc = np.zeros(1 << n)

    def pauli(psi, op):
        if op[0] == "rx":
            return _aplicar_1q(psi, _PAULIS[rng.integers(1, 4)], op[1])
        k = rng.integers(1, 16)
        psi = _aplicar_1q(psi, _PAULIS[k // 4], op[1])
        return _aplicar_1q(psi, _PAULIS[k % 4], op[2])

    for _ in range(trayectorias):
        i0 = rng.choice(len(ops), p=primero)
        psi = pauli(prefijo[i0 + 1], ops[i0])
        errores = rng.random(len(ops)) < p
        for i in range(i0 + 1, len(ops)):
            psi = _aplicar(psi, n, ops[i], mats[i])
            if errores[i]:
                psi = pauli(psi, ops[i])
        acc += np.abs(psi) ** 2
    return _error_lectura(P0 * ideal + (1 - P0) * acc / trayectorias, n, lectura)


def _error_lectura(probs, n, eps):
    if eps <= 0:
        return probs
    t = probs.reshape((2,) * n)
    M = np.array([[1 - eps, eps], [eps, 1 - eps]])
    for ax in range(n):
        t = np.moveaxis(np.tensordot(M, t, axes=([1], [ax])), 0, ax)
    return t.reshape(-1)


def recursos(ops: list[tuple]) -> dict:
    """Conteo de compuertas y fidelidad estimada en IonQ Forte (1 ZZ por RXX/RYY)."""
    n2 = sum(1 for op in ops if op[0] != "rx")
    n1 = sum(1 for op in ops if op[0] == "rx")
    return {"compuertas_2q": n2, "rotaciones_laser": n1, "zz_forte_estimadas": n2,
            "fidelidad_estimada": float(0.996 ** n2 * 0.9998 ** (n1 + 2 * n2))}
