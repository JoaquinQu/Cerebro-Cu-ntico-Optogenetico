"""Flujo completo contra un IonQ simulado: calibración → envío → resultado → análisis."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from _helpers import random_graph  # noqa: F401
import mock_ionq
from cerebro import config
from cerebro.ionq import IonQClient, IonQError
from cerebro.ionq import experiment


class TestIonQFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = mock_ionq.start()
        cls.tmp = tempfile.TemporaryDirectory()
        experiment.JOBS_DIR = Path(cls.tmp.name)
        cls.client = IonQClient(api_key="test-key", base_url=cls.url)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_endianness(self):
        self.assertTrue(experiment.endianness_check(self.client))

    def test_native_and_qis_jobs_match_theory(self):
        for gateset, mode in (("native", "givens"), ("qis", "givens"), ("native", "trotter")):
            rec = experiment.submit_microcircuit(self.client, gateset=gateset, mode=mode, steps=6, t=25.0,
                                                 sources=["AVM"])
            rec = experiment.refresh_record(self.client, rec["job_id"])
            self.assertEqual(rec["status"], "completed")
            a = rec["analysis"]
            tol = 1e-6 if mode == "givens" else 0.05  # el mock es ideal: sólo queda error de Trotter
            self.assertLess(a["tvd_raw"], tol)
            self.assertAlmostEqual(a["accepted_fraction"], 1.0, places=6)

    def test_qpu_is_blocked_by_default(self):
        self.assertFalse(config.ALLOW_QPU)
        with self.assertRaises(IonQError):
            self.client.submit({"backend": "qpu.forte-1"})

    def test_records_listed(self):
        experiment.submit_microcircuit(self.client, mode="givens")
        self.assertGreaterEqual(len(experiment.list_records()), 1)


if __name__ == "__main__":
    unittest.main()
