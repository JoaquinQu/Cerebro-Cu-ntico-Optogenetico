"""Convergencia de Trotter y exactitud del modo Givens (docs/TEORIA.md §6)."""

import unittest

import numpy as np

from _helpers import random_graph
from cerebro.analysis import postselect, tvd
from cerebro.circuits import build_microcircuit, probabilities, run_statevector
from cerebro.hamiltonian import evolve_exact, laser_state


class TestTrotter(unittest.TestCase):
    def setUp(self):
        self.J = random_graph(5, density=0.8, seed=4)
        self.t = 4.0
        self.psi_exact = evolve_exact(self.J, [0], np.pi, self.t)

    def _err(self, r, order):
        c = build_microcircuit(self.J, [0], np.pi, self.t, steps=r, order=order)
        return np.linalg.norm(run_statevector(c) - self.psi_exact)

    def test_first_order_scaling(self):
        e1, e2 = self._err(8, 1), self._err(16, 1)
        self.assertAlmostEqual(e1 / e2, 2.0, delta=0.35)  # O(1/r)

    def test_second_order_scaling(self):
        e1, e2 = self._err(8, 2), self._err(16, 2)
        self.assertAlmostEqual(e1 / e2, 4.0, delta=0.6)  # O(1/r²)

    def test_converges(self):
        self.assertLess(self._err(64, 2), 1e-3)


class TestGivens(unittest.TestCase):
    def test_givens_reproduces_distribution(self):
        J = random_graph(7, seed=9)
        for t in (0.5, 3.0, 11.0):
            for theta in (np.pi, 1.2):
                c = build_microcircuit(J, [3], theta, t, mode="givens")
                exact = np.abs(evolve_exact(J, [3], theta, t)) ** 2
                self.assertLess(tvd(probabilities(c), exact), 1e-10)
                self.assertLessEqual(sum(g.name == "hop" for g in c.gates), 6)  # ≤ n−1


class TestPostselection(unittest.TestCase):
    def test_removes_forbidden_sector(self):
        n = 4
        p = np.full(1 << n, 1 / 16)
        ps, acc = postselect(p, n, 1)
        self.assertAlmostEqual(acc, 5 / 16)
        self.assertAlmostEqual(ps.sum(), 1.0)
        self.assertEqual(ps[3], 0.0)  # |0011⟩ tiene 2 excitaciones

    def test_laser_state(self):
        psi = laser_state(3, [1], np.pi / 2)
        self.assertAlmostEqual(abs(psi[0]) ** 2, 0.5)
        self.assertAlmostEqual(abs(psi[2]) ** 2, 0.5)


class TestNoisySimulator(unittest.TestCase):
    """El estimador estratificado de trayectorias reproduce el canal despolarizante exacto."""

    def test_matches_density_matrix(self):
        from cerebro.circuits import Circuit, noisy_probabilities
        from cerebro.circuits.ir import I2, X, Y, Z

        n = 3
        c = Circuit(n)
        c.add("rx", [0], [2.0]).add("hop", [0, 1], [1.1]).add("hop", [1, 2], [0.7]).add("gpi2", [2], [0.3])
        f1, f2 = 0.97, 0.9  # ruido exagerado para que el efecto sea visible
        P = [I2, X, Y, Z]

        def op(mats):
            out = np.array([[1.0 + 0j]])
            for q in reversed(range(n)):  # qubit n-1 = factor izquierdo
                out = np.kron(out, mats.get(q, I2))
            return out

        def full(g):
            from cerebro.circuits.simulator import run_statevector
            cols = []
            for k in range(1 << n):
                e = np.zeros(1 << n, complex)
                e[k] = 1
                cc = Circuit(n)
                cc.gates = [g]
                cols.append(run_statevector(cc, e))
            return np.array(cols).T

        rho = np.zeros((1 << n, 1 << n), complex)
        rho[0, 0] = 1
        for g in c.gates:
            U = full(g)
            rho = U @ rho @ U.conj().T
            if len(g.qubits) == 2:
                p = 1 - f2
                acc = (1 - p) * rho
                for k in range(1, 16):
                    K = op({g.qubits[0]: P[k // 4], g.qubits[1]: P[k % 4]})
                    acc += p / 15 * K @ rho @ K.conj().T
                rho = acc
            else:
                p = 1 - f1
                acc = (1 - p) * rho
                for k in range(1, 4):
                    K = op({g.qubits[0]: P[k]})
                    acc += p / 3 * K @ rho @ K.conj().T
                rho = acc
        exact = np.real(np.diag(rho))
        est = noisy_probabilities(c, f1, f2, readout_error=0.0, trajectories=4000, seed=1)
        self.assertLess(0.5 * np.abs(est - exact).sum(), 0.02)


if __name__ == "__main__":
    unittest.main()
