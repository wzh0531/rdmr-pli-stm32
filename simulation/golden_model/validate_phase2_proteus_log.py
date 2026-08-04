"""Validate a complete Phase-2 Proteus log against the formal host model."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys

import numpy as np

from formal_algorithms import run_formal_algorithm
from signal_protocol import ExperimentConfig, generate_signal


ROOT = Path(__file__).resolve().parents[2]
EXECUTION_CONFIG_PATH = (
    ROOT / "config" / "firmware-execution__rdmr-pli__phase2__v0.3.1.json"
)
BLOCK_SIZE = 50
SAMPLE_COUNT = 8000
VALUE_SCALE = 1_000_000
FREQUENCY_SCALE = 1000
ENERGY_SCALE = 1_000_000


def parse_key_values(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in line.split(",")[1:]:
        key, value = item.split("=", 1)
        values[key] = value
    return values


def scaled_i32(value: float, scale: int) -> int:
    scaled = value * scale
    return int(np.clip(scaled, np.iinfo(np.int32).min, np.iinfo(np.int32).max))


def scaled_u32(value: float, scale: int) -> int:
    scaled = value * scale
    return int(np.clip(scaled, 0, np.iinfo(np.uint32).max))


def accumulate_energy(values: np.ndarray) -> np.float32:
    total = np.float32(0.0)
    for value in values.astype(np.float32, copy=False):
        total = np.float32(total + np.float32(value * value))
    return total


def validate(log_path: Path) -> dict[str, object]:
    execution = json.loads(EXECUTION_CONFIG_PATH.read_text(encoding="utf-8"))
    expected_columns = list(execution["columns"])
    lines = log_path.read_text(encoding="utf-8-sig").splitlines()
    errors: list[str] = []
    warnings: list[str] = []

    if len(lines) < 5:
        return {"status": "FAIL", "errors": ["log is too short"]}
    if not lines[0].startswith("BOOT,"):
        errors.append("missing BOOT")
    if not lines[1].startswith("CONFIG,"):
        errors.append("missing CONFIG")
    if lines[2].split(",") != expected_columns:
        errors.append("header does not match execution config")
    if not lines[-2].startswith("STATS,"):
        errors.append("missing STATS")
    if not lines[-1].startswith("DONE,"):
        errors.append("missing DONE")

    boot = parse_key_values(lines[0]) if lines[0].startswith("BOOT,") else {}
    config = (
        parse_key_values(lines[1])
        if lines[1].startswith("CONFIG,")
        else {}
    )
    stats = (
        parse_key_values(lines[-2])
        if lines[-2].startswith("STATS,")
        else {}
    )
    done = (
        parse_key_values(lines[-1])
        if lines[-1].startswith("DONE,")
        else {}
    )
    required_metadata = {
        "protocol": "cssp-rdmr-pli-v0.3.0",
        "implementation": "0.3.1",
        "schema": "rdmr-block-csv-v2",
        "firmware_revision": "13",
    }
    for key, expected in required_metadata.items():
        if boot.get(key) != expected:
            errors.append(f"BOOT {key} mismatch")
        if config.get(key) != expected:
            errors.append(f"CONFIG {key} mismatch")
    required_config = {
        "run_id": "1",
        "scenario_id": "101",
        "algorithm": "1",
        "trajectory": "1",
        "noise": "0",
        "near_line": "0",
        "seed": "0",
        "fs_hz": "1000",
        "sample_count": "8000",
        "block_size": "50",
        "pli_amplitude_u6": "500000",
    }
    for key, expected in required_config.items():
        if config.get(key) != expected:
            errors.append(f"CONFIG {key} mismatch")

    data_lines = lines[3:-2]
    rows = list(csv.DictReader([lines[2], *data_lines]))
    if len(rows) != SAMPLE_COUNT // BLOCK_SIZE:
        errors.append(f"expected 160 rows, got {len(rows)}")
    expected_n = list(range(BLOCK_SIZE, SAMPLE_COUNT + 1, BLOCK_SIZE))
    observed_n = [int(row["n"]) for row in rows]
    if observed_n != expected_n:
        errors.append("n is not the exact 50..8000 sequence")
    if any(len(line.split(",")) != len(expected_columns) for line in data_lines):
        errors.append("one or more data rows do not have 21 columns")
    if any(int(row["numeric_flags"]) != 0 for row in rows):
        errors.append("numeric_flags contains a nonzero value")
    if any(int(row["tracker_calls"]) != 0 for row in rows):
        errors.append("A1 tracker_calls must remain zero")
    if any(int(row["state"]) != 3 for row in rows):
        errors.append("A1 state must remain FIXED=3")

    formal_config = ExperimentConfig(
        algorithm="A1",
        trajectory="F1",
        pli_amplitude=0.50,
        noise="none",
        near_line="N0",
        seed=0,
        sample_count=SAMPLE_COUNT,
        log_schema_version="rdmr-block-csv-v2",
    )
    signals = generate_signal(formal_config)
    result = run_formal_algorithm(signals.input, 1)
    compared_fields = [
        "input",
        "clean",
        "output",
        "true_frequency",
        "estimated_frequency",
        "estimated_frequency_next",
        "residual_ratio",
        "desired_energy",
        "input_error_energy",
        "output_error_energy",
    ]
    maximum_absolute_difference = {field: 0 for field in compared_fields}

    for row_index, row in enumerate(rows):
        block_start = row_index * BLOCK_SIZE
        block_end = block_start + BLOCK_SIZE
        index = block_end - 1
        input_error = np.float32(
            signals.input[block_start:block_end]
            - signals.clean[block_start:block_end]
        )
        output_error = np.float32(
            result.output[block_start:block_end]
            - signals.clean[block_start:block_end]
        )
        expected = {
            "input": scaled_i32(float(signals.input[index]), VALUE_SCALE),
            "clean": scaled_i32(float(signals.clean[index]), VALUE_SCALE),
            "output": scaled_i32(float(result.output[index]), VALUE_SCALE),
            "true_frequency": scaled_i32(
                float(signals.true_frequency_hz[index]),
                FREQUENCY_SCALE,
            ),
            "estimated_frequency": scaled_i32(
                float(result.frequency_used_hz[index]),
                FREQUENCY_SCALE,
            ),
            "estimated_frequency_next": scaled_i32(
                float(result.frequency_next_hz[index]),
                FREQUENCY_SCALE,
            ),
            "residual_ratio": scaled_i32(
                float(result.residual_ratio[index]),
                VALUE_SCALE,
            ),
            "desired_energy": scaled_u32(
                float(accumulate_energy(signals.clean[block_start:block_end])),
                ENERGY_SCALE,
            ),
            "input_error_energy": scaled_u32(
                float(accumulate_energy(input_error)),
                ENERGY_SCALE,
            ),
            "output_error_energy": scaled_u32(
                float(accumulate_energy(output_error)),
                ENERGY_SCALE,
            ),
        }
        for field in compared_fields:
            difference = abs(int(row[field]) - expected[field])
            maximum_absolute_difference[field] = max(
                maximum_absolute_difference[field],
                difference,
            )

    strict_tolerances = {
        "input": 3,
        "clean": 3,
        "true_frequency": 1,
        "estimated_frequency": 1,
        "estimated_frequency_next": 1,
    }
    for field, tolerance in strict_tolerances.items():
        difference = maximum_absolute_difference[field]
        if difference > tolerance:
            errors.append(
                f"{field} maximum difference {difference} exceeds "
                f"strict tolerance {tolerance}"
            )
    adaptive_diagnostic_ceilings = {
        "output": 10_000,
        "residual_ratio": 60_000,
        "desired_energy": 300,
        "input_error_energy": 32,
        "output_error_energy": 35_000,
    }
    for field, ceiling in adaptive_diagnostic_ceilings.items():
        difference = maximum_absolute_difference[field]
        if difference > ceiling:
            errors.append(
                f"{field} maximum difference {difference} exceeds "
                f"cross-toolchain diagnostic ceiling {ceiling}"
            )
        elif difference != 0:
            warnings.append(
                f"{field} is not pointwise bit-exact; maximum scaled "
                f"difference is {difference}"
            )

    cycle_values = [int(row["cycles"]) for row in rows]
    cycle_means = [int(row["block_cycles_mean"]) for row in rows]
    cycle_p95 = [int(row["block_cycles_p95"]) for row in rows]
    if any(value <= 0 for value in cycle_values + cycle_means + cycle_p95):
        errors.append("DWT cycle fields contain zero or negative values")
    if any(p95 > maximum for p95, maximum in zip(cycle_p95, cycle_values)):
        errors.append("block P95 exceeds block maximum")
    if any(value >= 72_000 for value in cycle_values):
        errors.append("a block maximum violates the 1 ms deadline")

    if stats.get("rows") != "160" or stats.get("cycles_count") != "8000":
        errors.append("STATS row or cycle count mismatch")
    if stats.get("deadline_violations") != "0":
        errors.append("STATS reports deadline violations")
    if stats.get("numeric_faults") != "0":
        errors.append("STATS reports numeric faults")
    if stats.get("tracker_cycle_count") != "0":
        errors.append("A1 tracker cycle count must be zero")
    if done != {"rows": "160", "status": "PASS"}:
        errors.append("DONE marker is not PASS with 160 rows")

    desired_total = sum(int(row["desired_energy"]) for row in rows)
    input_error_total = sum(int(row["input_error_energy"]) for row in rows)
    output_error_total = sum(int(row["output_error_energy"]) for row in rows)
    input_snr_db = 10.0 * math.log10(desired_total / input_error_total)
    output_snr_db = 10.0 * math.log10(desired_total / output_error_total)
    formal_desired_total = float(
        np.sum(signals.clean.astype(np.float64) ** 2)
    )
    formal_input_error_total = float(
        np.sum(
            (signals.input - signals.clean).astype(np.float64) ** 2
        )
    )
    formal_output_error_total = float(
        np.sum(
            (result.output - signals.clean).astype(np.float64) ** 2
        )
    )
    formal_input_snr_db = 10.0 * math.log10(
        formal_desired_total / formal_input_error_total
    )
    formal_output_snr_db = 10.0 * math.log10(
        formal_desired_total / formal_output_error_total
    )
    output_snr_difference_db = output_snr_db - formal_output_snr_db
    if abs(output_snr_difference_db) > 0.1:
        errors.append(
            "Proteus versus formal output SNR differs by more than 0.1 dB"
        )
    deadline_cycles = int(stats.get("deadline_cycles", "0"))
    cycles_max = int(stats.get("cycles_max", "0"))

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "log_path": str(log_path.resolve()),
        "row_count": len(rows),
        "column_count": len(expected_columns),
        "metadata": {
            "protocol": boot.get("protocol"),
            "implementation": boot.get("implementation"),
            "schema": boot.get("schema"),
            "firmware_revision": boot.get("firmware_revision"),
            "algorithm": config.get("algorithm"),
            "trajectory": config.get("trajectory"),
            "seed": config.get("seed"),
        },
        "golden_model_comparison": {
            "maximum_absolute_difference_scaled_units":
                maximum_absolute_difference,
            "strict_signal_and_frequency_tolerances_scaled_units":
                strict_tolerances,
            "adaptive_path_diagnostic_ceilings_scaled_units":
                adaptive_diagnostic_ceilings,
            "pointwise_algorithm_bit_exact": not warnings,
            "output_snr_difference_db": output_snr_difference_db,
        },
        "performance": {
            "cycles_mean": int(stats.get("cycles_mean", "0")),
            "cycles_median": int(stats.get("cycles_median", "0")),
            "cycles_p95": int(stats.get("cycles_p95", "0")),
            "cycles_max": cycles_max,
            "deadline_cycles": deadline_cycles,
            "deadline_violations": int(
                stats.get("deadline_violations", "0")
            ),
            "maximum_deadline_utilization":
                cycles_max / deadline_cycles if deadline_cycles else None,
        },
        "signal_metrics": {
            "input_snr_db": input_snr_db,
            "output_snr_db": output_snr_db,
            "snr_improvement_db": output_snr_db - input_snr_db,
            "formal_input_snr_db": formal_input_snr_db,
            "formal_output_snr_db": formal_output_snr_db,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log_path", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.log_path)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    print(payload)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
