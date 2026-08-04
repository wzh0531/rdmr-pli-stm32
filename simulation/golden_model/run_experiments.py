"""Run the initial benchmark matrix for the RDMR-PLI golden model."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from rdmr_pli import (
    CancellerConfig,
    calculate_metrics,
    run_fixed_notch,
    run_quadrature_nlms,
    synthesize_sensor_signal,
)


PROFILES = (
    "constant_49",
    "constant_50",
    "constant_51",
    "ramp_up",
    "ramp_down",
    "step",
)
AMPLITUDES = (0.35, 0.70, 1.05)
SEEDS = (11, 29, 47)


def main() -> None:
    config = CancellerConfig()
    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, float | int | str]] = []

    for profile in PROFILES:
        for amplitude in AMPLITUDES:
            for seed in SEEDS:
                clean, interference, observed, true_frequency = (
                    synthesize_sensor_signal(
                        duration_s=8.0,
                        fs=config.fs,
                        frequency_profile=profile,
                        interference_amplitude=amplitude,
                        seed=seed,
                    )
                )

                notch_output = run_fixed_notch(observed, config.fs)
                notch_metrics = calculate_metrics(clean, interference, notch_output)
                rows.append(
                    {
                        "profile": profile,
                        "amplitude": amplitude,
                        "seed": seed,
                        "algorithm": "fixed_notch",
                        "tracker_calls": 0,
                        "tracker_reduction_pct": 100.0,
                        **notch_metrics,
                    }
                )

                results = {
                    mode: run_quadrature_nlms(observed, config, mode)
                    for mode in ("fixed", "full_rate", "residual_multirate")
                }
                full_rate_calls = results["full_rate"].tracker_calls
                for mode, result in results.items():
                    metrics = calculate_metrics(
                        clean,
                        interference,
                        result.output,
                        true_frequency,
                        result.frequency_hz,
                    )
                    reduction = (
                        100.0
                        * (full_rate_calls - result.tracker_calls)
                        / max(full_rate_calls, 1)
                    )
                    rows.append(
                        {
                            "profile": profile,
                            "amplitude": amplitude,
                            "seed": seed,
                            "algorithm": mode,
                            "tracker_calls": result.tracker_calls,
                            "tracker_reduction_pct": reduction,
                            **metrics,
                        }
                    )

    fieldnames = list(
        dict.fromkeys(
            key
            for row in rows
            for key in row.keys()
        )
    )
    with (output_dir / "benchmark_raw.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary_rows: list[dict[str, float | str]] = []
    algorithms = sorted({str(row["algorithm"]) for row in rows})
    for algorithm in algorithms:
        subset = [row for row in rows if row["algorithm"] == algorithm]
        summary_rows.append(
            {
                "algorithm": algorithm,
                "mean_suppression_db": float(
                    np.mean([float(row["suppression_db"]) for row in subset])
                ),
                "mean_output_snr_db": float(
                    np.mean([float(row["output_snr_db"]) for row in subset])
                ),
                "mean_tracker_calls": float(
                    np.mean([float(row["tracker_calls"]) for row in subset])
                ),
                "mean_tracker_reduction_pct": float(
                    np.mean(
                        [float(row["tracker_reduction_pct"]) for row in subset]
                    )
                ),
            }
        )

    with (output_dir / "benchmark_summary.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    for row in summary_rows:
        print(
            f"{row['algorithm']:20s} "
            f"supp={row['mean_suppression_db']:7.2f} dB "
            f"snr={row['mean_output_snr_db']:7.2f} dB "
            f"calls={row['mean_tracker_calls']:7.2f} "
            f"reduction={row['mean_tracker_reduction_pct']:6.1f}%"
        )


if __name__ == "__main__":
    main()
