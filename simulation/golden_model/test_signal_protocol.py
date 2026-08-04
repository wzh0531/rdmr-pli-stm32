"""Deterministic checks for the v0.3.0 cross-platform signal contract."""

from __future__ import annotations

import re
import unittest

import numpy as np

from signal_protocol import (
    ExperimentConfig,
    generate_signal,
    load_protocol,
    protocol_path,
)


class SignalProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.protocol = load_protocol()

    def _config(
        self,
        trajectory: str,
        noise: str = "none",
        seed: int = 0,
        near_line: str = "N0",
    ) -> ExperimentConfig:
        return ExperimentConfig(
            algorithm="A3",
            trajectory=trajectory,
            pli_amplitude=0.50,
            noise=noise,
            near_line=near_line,
            seed=seed,
        )

    def test_machine_config_contains_phase1_required_fields(self) -> None:
        required = {
            "algorithm_ids",
            "trajectory_ids",
            "noise_ids",
            "seed_partitions",
            "sample_rate_hz",
            "sample_count",
            "log_schema_version",
        }
        self.assertTrue(required.issubset(self.protocol))
        self.assertEqual(
            self.protocol["algorithm_ids"],
            {"A0": 0, "A1": 1, "A2": 2, "A3": 3},
        )
        self.assertEqual(
            self.protocol["seed_partitions"]["development"],
            [0, 1, 2, 3, 4],
        )

    def test_generated_c_header_keeps_algorithm_ids(self) -> None:
        header = (
            protocol_path().parents[1]
            / "firmware"
            / "core"
            / "rdmr_experiment_config.h"
        ).read_text(encoding="utf-8")
        expected = {
            "RDMR_ALGORITHM_A0_FIXED_NOTCH": 0,
            "RDMR_ALGORITHM_A1_FIXED_NLMS": 1,
            "RDMR_ALGORITHM_A2_FULL_RATE": 2,
            "RDMR_ALGORITHM_A3_RESIDUAL_MULTIRATE": 3,
        }
        for symbol, value in expected.items():
            self.assertRegex(
                header,
                re.compile(rf"\b{symbol}\s*=\s*{value}\b"),
            )

    def test_f1_boundary_and_phase_continuity_inputs_are_finite(self) -> None:
        arrays = generate_signal(self._config("F1", "snr_20_db", seed=4))
        self.assertEqual(float(arrays.true_frequency_hz[3999]), 49.0)
        self.assertEqual(float(arrays.true_frequency_hz[4000]), 51.0)
        self.assertTrue(np.all(np.isfinite(arrays.input)))
        self.assertLess(
            abs(
                float(arrays.interference[4000])
                - float(arrays.interference[3999])
            ),
            0.5,
        )

    def test_rng_substreams_keep_f5_path_and_phase_noise_independent(self) -> None:
        without_noise = generate_signal(self._config("F5", "none", seed=3))
        with_noise = generate_signal(
            self._config("F5", "snr_20_db", seed=3)
        )
        np.testing.assert_array_equal(
            without_noise.true_frequency_hz,
            with_noise.true_frequency_hz,
        )
        np.testing.assert_array_equal(
            without_noise.interference,
            with_noise.interference,
        )
        self.assertFalse(np.array_equal(without_noise.input, with_noise.input))

    def test_seed_changes_initial_phase_without_changing_clean_signal(self) -> None:
        seed_zero = generate_signal(self._config("F0", seed=0))
        seed_one = generate_signal(self._config("F0", seed=1))
        np.testing.assert_array_equal(seed_zero.clean, seed_one.clean)
        self.assertFalse(
            np.array_equal(seed_zero.interference, seed_one.interference)
        )

    def test_all_frozen_trajectory_definitions_remain_in_range(self) -> None:
        for trajectory in ("F0", "F1", "F2", "F3", "F4", "F5"):
            arrays = generate_signal(self._config(trajectory, seed=2))
            self.assertGreaterEqual(
                float(np.min(arrays.true_frequency_hz)),
                45.0,
            )
            self.assertLessEqual(
                float(np.max(arrays.true_frequency_hz)),
                55.0,
            )
            self.assertEqual(arrays.input.shape, (8000,))


if __name__ == "__main__":
    unittest.main()
