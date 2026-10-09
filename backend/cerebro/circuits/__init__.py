"""Circuitos: IR, simulador, constructores (láser/Trotter/Givens) y compilación a IonQ."""

from .ir import Circuit, Gate, gate_matrix
from .builders import build_microcircuit, givens_walk, laser, trotter_xy
from .compile_ionq import (
    compile_native,
    lower_to_native,
    lower_to_qis,
    propagate_virtual_z,
    to_ionq_input,
    to_openqasm2,
)
from .simulator import (
    circuit_unitary,
    noisy_probabilities,
    probabilities,
    run_statevector,
    sample_counts,
)

__all__ = [
    "Circuit", "Gate", "gate_matrix", "build_microcircuit", "givens_walk", "laser", "trotter_xy",
    "compile_native", "lower_to_native", "lower_to_qis", "propagate_virtual_z", "to_ionq_input",
    "to_openqasm2", "circuit_unitary", "noisy_probabilities", "probabilities", "run_statevector",
    "sample_counts",
]
