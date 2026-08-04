"""Lightweight regression checks for the golden model."""

from __future__ import annotations

import unittest

import numpy as np

from rdmr_pli import (
    CancellerConfig,
    calculate_metrics,
    run_quadrature_nlms,
    synthesize_sensor_signal,
)


class GoldenModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = CancellerConfig()
        self.clean, self.interference, self.observed, self.true_frequency = (
            synthesize_sensor_signal(
                duration_s=6.0,
                fs=self.config.fs,
                frequency_profile="ramp_up",
                interference_amplitude=0.70,
                seed=7,
            )
        )

    def test_synthesis_shapes_and_finiteness(self) -> None:
        self.assertEqual(self.clean.shape, self.observed.shape)
        self.assertTrue(np.all(np.isfinite(self.observed)))
        self.assertAlmostEqual(float(self.true_frequency[0]), 49.0)
        self.assertAlmostEqual(float(self.true_frequency[-1]), 51.0)

    def test_multirate_reduces_tracker_calls(self) -> None:
        full_rate = run_quadrature_nlms(
            self.observed,
            self.config,
            "full_rate",
        )
        multirate = run_quadrature_nlms(
            self.observed,
            self.config,
            "residual_multirate",
        )
        self.assertLess(multirate.tracker_calls, full_rate.tracker_calls)

    def test_multirate_improves_over_uncancelled_input(self) -> None:
        multirate = run_quadrature_nlms(
            self.observed,
            self.config,
            "residual_multirate",
        )
        input_metrics = calculate_metrics(
            self.clean,
            self.interference,
            self.observed,
        )
        output_metrics = calculate_metrics(
            self.clean,
            self.interference,
            multirate.output,
        )
        self.assertGreater(
            output_metrics["output_snr_db"],
            input_metrics["output_snr_db"] + 6.0,
        )


if __name__ == "__main__":
    unittest.main()
