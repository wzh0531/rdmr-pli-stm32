"""Regression checks for the formal A0-A3 float32 execution path."""

from __future__ import annotations

import unittest

import numpy as np

from formal_algorithms import run_formal_algorithm
from signal_protocol import ExperimentConfig, generate_signal


class FormalAlgorithmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = ExperimentConfig(
            algorithm="A3",
            trajectory="F1",
            pli_amplitude=0.50,
            noise="none",
            near_line="N0",
            seed=0,
            sample_count=2000,
        )
        cls.signals = generate_signal(config)
        cls.results = {
            algorithm_id: run_formal_algorithm(
                cls.signals.input,
                algorithm_id,
            )
            for algorithm_id in range(4)
        }

    def test_all_algorithm_outputs_are_finite(self) -> None:
        for algorithm_id in range(4):
            result = self.results[algorithm_id]
            self.assertEqual(result.output.dtype, np.float32)
            self.assertTrue(np.all(np.isfinite(result.output)))
            self.assertTrue(np.all(np.isfinite(result.frequency_used_hz)))

    def test_algorithm_ids_have_expected_tracker_semantics(self) -> None:
        a0 = self.results[0]
        a1 = self.results[1]
        a2 = self.results[2]
        a3 = self.results[3]
        self.assertEqual(int(a0.tracker_calls[-1]), 0)
        self.assertEqual(int(a1.tracker_calls[-1]), 0)
        self.assertEqual(int(a2.tracker_calls[-1]), 40)
        self.assertLess(int(a3.tracker_calls[-1]), int(a2.tracker_calls[-1]))

    def test_frequency_used_and_next_have_explicit_block_boundary(self) -> None:
        result = self.results[2]
        self.assertEqual(float(result.frequency_used_hz[49]), 50.0)
        self.assertEqual(float(result.frequency_next_hz[49]), 50.0)
        self.assertEqual(int(result.tracker_calls[49]), 1)
        self.assertEqual(
            float(result.frequency_used_hz[50]),
            float(result.frequency_next_hz[49]),
        )


if __name__ == "__main__":
    unittest.main()
