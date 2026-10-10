"""Figuras de Qiskit (matplotlib) para la página: circuito con `draw("mpl")` e histograma.

Se devuelven como data URI SVG para usarlas en un <img>: así cada figura queda aislada
(matplotlib repite los id internos de sus SVG) y no se ejecuta nada en la página.
"""

from __future__ import annotations

import base64
import io

ESTILO = "iqp-dark"
TOPE_BARRAS = 14


def _matplotlib():
    import matplotlib

    matplotlib.use("Agg")  # sólo se exporta a SVG; en Pyodide evita el backend interactivo
    matplotlib.rcParams["svg.fonttype"] = "none"  # texto como texto: SVG más liviano
    from matplotlib import pyplot as plt

    return plt


def _svg(fig) -> str:
    plt = _matplotlib()
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue().encode("utf-8")).decode("ascii")


def con_nombres(qc, nombres: list[str]):
    """Copia del circuito para dibujar, con un registro de 1 qubit por neurona (el cable lleva su nombre)."""
    from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister

    regs = [QuantumRegister(1, nm) for nm in nombres]
    dq = QuantumCircuit(*regs, ClassicalRegister(qc.num_clbits, "c")) if qc.num_clbits else QuantumCircuit(*regs)
    dq.compose(qc, qubits=range(qc.num_qubits), clbits=range(qc.num_clbits), inplace=True)
    return dq


def circuito(qc, nombres: list[str], fold: int = 28) -> str:
    _matplotlib()
    fig = con_nombres(qc, nombres).draw("mpl", style=ESTILO, fold=fold)
    return _svg(fig)


def etiqueta_estado(bits: str, nombres: list[str]) -> str:
    """'0000000101' → 'AVM+AVDL' (qubit 0 = carácter de la derecha); no excitation → '∅'."""
    bits = bits.replace(" ", "")
    unos = [nombres[q] for q, b in enumerate(reversed(bits)) if b == "1"]
    if not unos:
        return "∅ (none)"
    return "+".join(unos) if len(unos) <= 3 else bits


def _agrupar(datos: dict, nombres: list[str]) -> dict:
    out: dict[str, float] = {}
    for k, v in datos.items():
        e = etiqueta_estado(str(k), nombres)
        out[e] = out.get(e, 0) + v
    return out


def histograma(conteos: dict, nombres: list[str], titulo: str) -> str:
    """Conteos medidos en el backend con plot_histogram de Qiskit."""
    plt = _matplotlib()
    from qiskit.visualization import plot_histogram

    with plt.style.context("dark_background"):
        fig = plot_histogram(_agrupar(conteos, nombres), number_to_keep=TOPE_BARRAS, sort="value_desc",
                             title=titulo, figsize=(9, 4), color="#ffb347", bar_labels=True)
    return _svg(fig)


def distribucion_ideal(qc, nombres: list[str], titulo: str) -> str:
    """Distribución ideal del circuito (Statevector de Qiskit, sin medir) con plot_distribution."""
    plt = _matplotlib()
    from qiskit.quantum_info import Statevector
    from qiskit.visualization import plot_distribution

    sv = Statevector.from_instruction(qc.remove_final_measurements(inplace=False))
    probs = {k: float(v) for k, v in sv.probabilities_dict().items() if v > 1e-6}
    with plt.style.context("dark_background"):
        fig = plot_distribution(_agrupar(probs, nombres), number_to_keep=TOPE_BARRAS, sort="value_desc",
                                title=titulo, figsize=(9, 4), color="#38e1ff", bar_labels=True)
    return _svg(fig)


def resumen_ops(qc) -> dict:
    return {str(k): int(v) for k, v in qc.count_ops().items()}
