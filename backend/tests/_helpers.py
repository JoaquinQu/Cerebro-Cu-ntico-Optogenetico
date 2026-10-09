import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def equal_up_to_phase(A, B, atol=1e-8):
    A, B = np.asarray(A), np.asarray(B)
    k = np.argmax(np.abs(B))
    ph = A.flat[k] / B.flat[k]
    return abs(abs(ph) - 1) < 1e-8 and np.allclose(A, ph * B, atol=atol)


def random_graph(n, density=0.6, seed=0):
    rng = np.random.default_rng(seed)
    J = np.triu(rng.random((n, n)) * (rng.random((n, n)) < density), 1)
    J = J + J.T
    return J / np.max(np.abs(np.linalg.eigvalsh(J)))
