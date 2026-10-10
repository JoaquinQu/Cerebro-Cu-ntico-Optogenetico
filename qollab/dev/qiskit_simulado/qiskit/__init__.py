"""Imitación MÍNIMA de Qiskit para probar el proyecto fuera de Qollab sin instalar Qiskit.

Sólo implementa lo que usa cerebro_q (QuantumCircuit con rx/rxx/ryy/measure, draw y
count_ops) y un backend que simula con numpy. Si tienes Qiskit instalado, el arnés
de desarrollo usa el Qiskit real y este paquete se ignora.
"""

import numpy as np

SIMULADO = True


class QuantumCircuit:
    def __init__(self, n_qubits, n_clbits=0, name="circuit"):
        self.num_qubits, self.num_clbits, self.name = n_qubits, n_clbits, name
        self.data = []
        self.medido = False

    def rx(self, theta, q):
        self.data.append(("rx", q, float(theta)))

    def rxx(self, theta, a, b):
        self.data.append(("rxx", a, b, float(theta)))

    def ryy(self, theta, a, b):
        self.data.append(("ryy", a, b, float(theta)))

    def measure(self, qubits, clbits):
        self.medido = True

    def count_ops(self):
        out = {}
        for op in self.data:
            out[op[0]] = out.get(op[0], 0) + 1
        if self.medido:
            out["measure"] = self.num_qubits
        return out

    def draw(self, output="text", fold=-1):
        lineas = [f"q_{q}: " for q in range(self.num_qubits)]
        for op in self.data[:60]:
            qs = op[1:2] if op[0] == "rx" else op[1:3]
            for q in range(self.num_qubits):
                lineas[q] += (f"[{op[0].upper()}]" if q in qs else "──────")[:6].ljust(6, "─")
        return "\n".join(lineas) + ("\n…" if len(self.data) > 60 else "")


class _Resultado:
    def __init__(self, conteos):
        self._c = conteos

    def get_counts(self, i=None):
        if i is None:
            return self._c[0] if len(self._c) == 1 else self._c
        return self._c[i]


class _Trabajo:
    def __init__(self, conteos):
        self._r = _Resultado(conteos)

    def result(self):
        return self._r

    def job_id(self):
        return "simulado-local"


class BackendSimulado:
    """Backend ideal: muestrea la distribución exacta del circuito (claves con q0 a la derecha)."""

    name = "local_dev_simulator"

    def __init__(self, semilla=3):
        self.rng = np.random.default_rng(semilla)

    def run(self, circuitos, shots=1000):
        from cerebro_q.circuitos import probabilidades_ideales

        lista = circuitos if isinstance(circuitos, (list, tuple)) else [circuitos]
        conteos = []
        for qc in lista:
            p = probabilidades_ideales(qc.data, qc.num_qubits)
            m = self.rng.multinomial(shots, p / p.sum())
            conteos.append({format(i, f"0{qc.num_qubits}b"): int(c) for i, c in enumerate(m) if c})
        return _Trabajo(conteos)
