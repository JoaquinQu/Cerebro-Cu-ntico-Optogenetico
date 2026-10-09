"""Las identidades de compilación a IonQ (docs/TEORIA.md §6.4) son exactas."""

import unittest

import numpy as np
from scipy.stats import unitary_group

from _helpers import equal_up_to_phase, random_graph
from cerebro.circuits import (
    Circuit,
    build_microcircuit,
    circuit_unitary,
    compile_native,
    lower_to_native,
    lower_to_qis,
    probabilities,
    propagate_virtual_z,
    to_ionq_input,
)
from cerebro.circuits.compile_ionq import _synth_1q, _zz_native
from cerebro.circuits.ir import X, Y, gate_matrix
from scipy.linalg import expm


class TestGateDefinitions(unittest.TestCase):
    def test_hop_is_xy_exponential(self):
        a = 0.83
        XX, YY = np.kron(X, X), np.kron(Y, Y)
        self.assertTrue(np.allclose(gate_matrix("hop", (a,)), expm(-1j * a * (XX + YY) / 2)))

    def test_ionq_matrices_from_docs(self):
        phi = 0.17
        e = np.exp(2j * np.pi * phi)
        self.assertTrue(np.allclose(gate_matrix("gpi", (phi,)), [[0, 1 / e], [e, 0]]))
        self.assertTrue(np.allclose(gate_matrix("gpi2", (phi,)), np.array([[1, -1j / e], [-1j * e, 1]]) / np.sqrt(2)))
        th = 0.13
        zz = gate_matrix("zz", (th,))
        self.assertTrue(np.allclose(np.diag(zz), np.exp(-1j * np.pi * th * np.array([1, -1, -1, 1]))))


class TestNativeLowering(unittest.TestCase):
    def test_hop_forte_aria_qis(self):
        for a in (0.3, 1.2, -0.7, 2.9):
            c = Circuit(2).add("hop", [0, 1], [a])
            U = circuit_unitary(c)
            self.assertTrue(equal_up_to_phase(circuit_unitary(lower_to_native(c, "forte")), U))
            self.assertTrue(equal_up_to_phase(circuit_unitary(lower_to_qis(c)), U))
            if abs(a) / 2 <= np.pi / 4:
                self.assertTrue(equal_up_to_phase(circuit_unitary(lower_to_native(c, "aria")), U))

    def test_rx_laser(self):
        for th in (0.4, 2.0, np.pi):
            c = Circuit(1).add("rx", [0], [th])
            self.assertTrue(equal_up_to_phase(circuit_unitary(lower_to_native(c)), circuit_unitary(c)))

    def test_zz_angle_reduction(self):
        for th in (0.1, 0.3, -0.1, -0.4, 0.6, 0.9):
            c = Circuit(2)
            c.gates = _zz_native(0, 1, th, "")
            ref = Circuit(2).add("zz", [0, 1], [th])
            self.assertTrue(equal_up_to_phase(circuit_unitary(c), circuit_unitary(ref)))
            for g in c.gates:
                if g.name == "zz":
                    self.assertTrue(0 <= g.params[0] <= 0.25 + 1e-12)

    def test_single_qubit_synthesis(self):
        for s in range(100):
            U = unitary_group.rvs(2, random_state=s)
            c = Circuit(1)
            c.gates = _synth_1q(U, 0, "")
            self.assertTrue(equal_up_to_phase(circuit_unitary(c), U))
            self.assertLessEqual(sum(g.name != "rz" for g in c.gates), 2)

    def test_virtual_z_propagation(self):
        rng = np.random.default_rng(0)
        n = 3
        c = Circuit(n)
        for _ in range(60):
            r = rng.integers(4)
            if r == 0:
                c.add("rz", [rng.integers(n)], [rng.normal() * 3])
            elif r == 1:
                c.add("gpi2", [rng.integers(n)], [rng.random()])
            elif r == 2:
                c.add("gpi", [rng.integers(n)], [rng.random()])
            else:
                a, b = rng.choice(n, 2, replace=False)
                c.add("zz", [a, b], [rng.random() * 0.25])
        p, frame = propagate_virtual_z(c)
        d = np.ones(1 << n, complex)
        for q in range(n):
            bit = (np.arange(1 << n) >> q) & 1
            d *= np.where(bit == 1, np.exp(1j * frame[q] / 2), np.exp(-1j * frame[q] / 2))
        self.assertTrue(equal_up_to_phase(circuit_unitary(c), np.diag(d) @ circuit_unitary(p)))
        self.assertNotIn("rz", {g.name for g in p.gates})

    def test_full_microcircuit_native_matches_logical(self):
        J = random_graph(5, seed=2)
        for mode in ("trotter", "givens"):
            c = build_microcircuit(J, [1], 2.2, 3.0, mode=mode, steps=2)
            nat = compile_native(c)
            self.assertTrue(np.allclose(probabilities(nat), probabilities(c), atol=1e-10))
            payload = to_ionq_input(nat)
            self.assertEqual(payload["gateset"], "native")
            self.assertTrue({op["gate"] for op in payload["circuit"]} <= {"gpi", "gpi2", "zz"})


if __name__ == "__main__":
    unittest.main()
