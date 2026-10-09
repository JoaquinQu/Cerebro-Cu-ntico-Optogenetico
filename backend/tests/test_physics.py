"""La física del modelo (docs/TEORIA.md §3–§5) verificada numéricamente."""

import unittest

import numpy as np

from _helpers import random_graph  # noqa: F401  (añade backend/ al path)
from cerebro.connectome import get_connectome
from cerebro.hamiltonian import (
    evolve_exact,
    firing_probabilities,
    marginals,
    walk_amplitudes,
    xy_hamiltonian,
)


class TestConnectome(unittest.TestCase):
    def test_shape_and_normalization(self):
        C = get_connectome()
        self.assertEqual(C.n, 302)
        self.assertTrue(np.allclose(C.J, C.J.T), "J debe ser simétrica (hermítica)")
        self.assertAlmostEqual(np.max(np.abs(np.linalg.eigvalsh(C.J))), 1.0, places=10)
        self.assertTrue(np.all(np.diag(C.J) == 0))

    def test_touch_neurons_present(self):
        C = get_connectome()
        for n in ["ALML", "ALMR", "AVM", "PLML", "PLMR", "PVM", "AVAL", "AVDL", "PVCL", "AVBL"]:
            self.assertIn(n, C.names)


class TestQuantumWalkEquivalence(unittest.TestCase):
    """Sector de una excitación del modelo XY ≡ quantum walk con hamiltoniano γJ."""

    def test_xy_single_excitation_equals_ctqw(self):
        n, gamma, theta = 6, 1.3, 2.1
        J = random_graph(n, seed=3)
        eig = np.linalg.eigh(J)
        for j in range(n):
            for t in (0.0, 0.7, 2.5):
                full = np.abs(evolve_exact(J, [j], theta, t, gamma)) ** 2
                pk = marginals(full, n)
                walk = firing_probabilities(eig, j, np.array([t]), theta, gamma)[0]
                self.assertTrue(np.allclose(pk, walk, atol=1e-10))

    def test_vacuum_probability_is_cos2(self):
        J = random_graph(5, seed=1)
        theta = 1.0
        psi = evolve_exact(J, [2], theta, 3.0)
        self.assertAlmostEqual(abs(psi[0]) ** 2, np.cos(theta / 2) ** 2, places=10)

    def test_excitation_number_conserved(self):
        n = 6
        H = xy_hamiltonian(random_graph(n, seed=5)).toarray()
        N = np.diag([bin(k).count("1") for k in range(1 << n)])
        self.assertTrue(np.allclose(H @ N, N @ H))
        self.assertTrue(np.allclose(H, H.conj().T))

    def test_full_network_norm(self):
        C = get_connectome()
        theta = 1.7
        P = firing_probabilities(C.eigh(), C.index("AVM"), np.linspace(0, 50, 7), theta)
        self.assertTrue(np.allclose(P.sum(axis=1), np.sin(theta / 2) ** 2))

    def test_amplitudes_unitary_at_t0(self):
        C = get_connectome()
        a = walk_amplitudes(C.eigh(), 10, np.array([0.0]))[0]
        e = np.zeros(C.n)
        e[10] = 1
        self.assertTrue(np.allclose(a, e, atol=1e-10))


if __name__ == "__main__":
    unittest.main()
