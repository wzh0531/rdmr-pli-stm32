"""Validate a raw STM32 Phase-8 UART log (Rev16 or later).

The structural verdict is separate from the observed real-time verdict.  A
complete log may be structurally valid while still missing the 50 ms budget.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys


SAMPLE_COUNT = 8000
BLOCK_SIZE = 50
EXPECTED_ROWS = SAMPLE_COUNT // BLOCK_SIZE
HARD_BLOCK_BUDGET = 3_600_000
TARGET_BLOCK_BUDGET = 2_880_000
SAMPLE_DEADLINE = 72_000
EXPECTED_COLUMNS = [
    "run_id", "scenario_id", "algorithm", "seed", "n", "input", "clean",
    "output", "true_frequency", "estimated_frequency",
    "estimated_frequency_next", "tracker_calls", "tracker_searches",
    "tracker_grid_evaluations", "state", "cycles", "block_cycles_total",
    "block_cycles_mean", "block_cycles_p95", "residual_ratio",
    "desired_energy", "input_error_energy", "output_error_energy",
    "numeric_flags",
]


def portable_log_path(log_path: Path) -> str:
    """Return a repository-relative path when the log is inside the checkout."""
    try:
        return log_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return log_path.name


def parse_key_values(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in line.split(",")[1:]:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        values[key] = value
    return values


def validate(
    log_path: Path,
    expected_scenario: int | None = None,
    expected_algorithm: int | None = None,
    expected_search_mode: int | None = None,
    expected_implementation: str = "0.4.1",
    expected_firmware_revision: int = 17,
) -> dict[str, object]:
    lines = log_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    errors: list[str] = []
    warnings: list[str] = []
    if len(lines) < 5:
        return {"status": "FAIL", "errors": ["log is too short"]}

    boot_index = next((i for i, line in enumerate(lines) if line.startswith("BOOT,")), None)
    config_index = next((i for i, line in enumerate(lines) if line.startswith("CONFIG,")), None)
    stats_index = next((i for i, line in enumerate(lines) if line.startswith("STATS,")), None)
    done_index = next((i for i, line in enumerate(lines) if line.startswith("DONE,")), None)
    if boot_index is None:
        errors.append("missing BOOT")
    if config_index is None:
        errors.append("missing CONFIG")
    if stats_index is None:
        errors.append("missing STATS")
    if done_index is None:
        errors.append("missing DONE")
    if errors:
        return {
            "status": "FAIL",
            "errors": errors,
            "log_path": portable_log_path(log_path),
        }

    header_index = config_index + 1
    boot = parse_key_values(lines[boot_index])
    config = parse_key_values(lines[config_index])
    stats = parse_key_values(lines[stats_index])
    done = parse_key_values(lines[done_index])
    observed_columns = lines[header_index].split(",")
    if observed_columns != EXPECTED_COLUMNS:
        errors.append("header does not match rdmr-block-csv-v3")

    required_metadata = {
        "protocol": "cssp-rdmr-pli-v0.5.0",
        "implementation": expected_implementation,
        "schema": "rdmr-block-csv-v3",
        "firmware_revision": str(expected_firmware_revision),
    }
    for key, expected in required_metadata.items():
        if boot.get(key) != expected:
            errors.append(f"BOOT {key} mismatch: {boot.get(key)!r}")
        if config.get(key) != expected:
            errors.append(f"CONFIG {key} mismatch: {config.get(key)!r}")

    scenario = int(config.get("scenario_id", "-1"))
    algorithm = int(config.get("algorithm", "-1"))
    search_mode = int(config.get("tracker_search_mode", "-1"))
    points_per_search = int(config.get("tracker_grid_points_max", "0"))
    if expected_scenario is not None and scenario != expected_scenario:
        errors.append(f"scenario mismatch: {scenario} != {expected_scenario}")
    if expected_algorithm is not None and algorithm != expected_algorithm:
        errors.append(f"algorithm mismatch: {algorithm} != {expected_algorithm}")
    if expected_search_mode is not None and search_mode != expected_search_mode:
        errors.append(f"search mode mismatch: {search_mode} != {expected_search_mode}")
    expected_points = 32 if search_mode == 1 else 201 if search_mode == 0 else 0
    if points_per_search != expected_points:
        errors.append(
            f"grid point metadata mismatch: {points_per_search} != {expected_points}"
        )

    data_lines = lines[header_index + 1:stats_index]
    rows = list(csv.DictReader([lines[header_index], *data_lines]))
    if len(rows) != EXPECTED_ROWS:
        errors.append(f"expected {EXPECTED_ROWS} rows, got {len(rows)}")
    if any(len(line.split(",")) != len(EXPECTED_COLUMNS) for line in data_lines):
        errors.append("one or more data rows have the wrong column count")
    if rows:
        expected_n = list(range(BLOCK_SIZE, SAMPLE_COUNT + 1, BLOCK_SIZE))
        observed_n = [int(row["n"]) for row in rows]
        if observed_n != expected_n:
            errors.append("n is not the exact 50..8000 sequence")
        if any(int(row["numeric_flags"]) != 0 for row in rows):
            errors.append("numeric_flags contains a nonzero value")

    calls = [int(row["tracker_calls"]) for row in rows]
    searches = [int(row["tracker_searches"]) for row in rows]
    evaluations = [int(row["tracker_grid_evaluations"]) for row in rows]
    if any(a > b for a, b in zip(searches, calls)):
        errors.append("tracker_searches exceeds tracker_calls")
    if any(b < a for a, b in zip(calls, calls[1:])):
        errors.append("tracker_calls is not monotonic")
    if any(b < a for a, b in zip(searches, searches[1:])):
        errors.append("tracker_searches is not monotonic")
    if any(b < a for a, b in zip(evaluations, evaluations[1:])):
        errors.append("tracker_grid_evaluations is not monotonic")
    if rows and evaluations[-1] != searches[-1] * points_per_search:
        errors.append("final grid evaluation total does not equal searches × points")

    sample_maxima = [int(row["cycles"]) for row in rows]
    block_totals = [int(row["block_cycles_total"]) for row in rows]
    block_means = [int(row["block_cycles_mean"]) for row in rows]
    block_p95 = [int(row["block_cycles_p95"]) for row in rows]
    if any(value <= 0 for value in sample_maxima + block_totals + block_means + block_p95):
        errors.append("one or more DWT cycle fields are zero or negative")
    if any(total < maximum for total, maximum in zip(block_totals, sample_maxima)):
        errors.append("a block total is smaller than its sample maximum")
    if any(p95 > maximum for p95, maximum in zip(block_p95, sample_maxima)):
        errors.append("a block P95 exceeds its sample maximum")

    if stats.get("rows") != str(EXPECTED_ROWS):
        errors.append("STATS row count mismatch")
    if stats.get("cycles_count") != str(SAMPLE_COUNT):
        errors.append("STATS sample cycle count mismatch")
    if stats.get("block_total_count") != str(EXPECTED_ROWS):
        errors.append("STATS block total count mismatch")
    if stats.get("deadline_cycles") != str(SAMPLE_DEADLINE):
        errors.append("STATS sample deadline is not 72,000 cycles")
    if stats.get("block_deadline_cycles") != str(HARD_BLOCK_BUDGET):
        errors.append("STATS block deadline is not 3,600,000 cycles")
    if stats.get("numeric_faults") != "0":
        errors.append("STATS reports numeric faults")
    if done != {"rows": str(EXPECTED_ROWS), "status": "PASS"}:
        errors.append("DONE marker is not PASS with 160 rows")

    observed_block_max = max(block_totals, default=0)
    stats_block_max = int(stats.get("block_total_max", "0"))
    if stats_block_max != observed_block_max:
        errors.append(
            f"STATS block max mismatch: {stats_block_max} != {observed_block_max}"
        )
    observed_sample_violations = sum(
        value >= SAMPLE_DEADLINE for value in sample_maxima
    )
    observed_block_violations = sum(
        value >= HARD_BLOCK_BUDGET for value in block_totals
    )
    if int(stats.get("deadline_violations", "-1")) != observed_sample_violations:
        errors.append("STATS sample deadline violation count mismatch")
    if (
        int(stats.get("block_deadline_violations", "-1"))
        != observed_block_violations
    ):
        errors.append("STATS block deadline violation count mismatch")
    if rows and int(stats.get("tracker_searches", "-1")) != searches[-1]:
        errors.append("STATS tracker search count mismatch")
    if rows and int(stats.get("tracker_grid_evaluations", "-1")) != evaluations[-1]:
        errors.append("STATS tracker grid evaluation count mismatch")
    if observed_block_max <= TARGET_BLOCK_BUDGET:
        realtime_verdict = "PASS_TARGET_20_PERCENT_MARGIN"
    elif observed_block_max < HARD_BLOCK_BUDGET:
        realtime_verdict = "PASS_HARD_BUDGET_ONLY"
    else:
        realtime_verdict = "FAIL_HARD_BLOCK_BUDGET"

    desired_total = sum(int(row["desired_energy"]) for row in rows)
    input_error_total = sum(int(row["input_error_energy"]) for row in rows)
    output_error_total = sum(int(row["output_error_energy"]) for row in rows)
    input_snr = (
        10.0 * math.log10(desired_total / input_error_total)
        if input_error_total > 0 else None
    )
    output_snr = (
        10.0 * math.log10(desired_total / output_error_total)
        if output_error_total > 0 else None
    )

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "log_path": portable_log_path(log_path),
        "metadata": {
            "implementation": config.get("implementation"),
            "firmware_revision": int(config.get("firmware_revision", "0")),
            "scenario_id": scenario,
            "algorithm": algorithm,
            "search_mode": search_mode,
            "points_per_search": points_per_search,
            "seed": int(config.get("seed", "0")),
        },
        "rows": len(rows),
        "tracker": {
            "calls": calls[-1] if calls else 0,
            "searches": searches[-1] if searches else 0,
            "grid_evaluations": evaluations[-1] if evaluations else 0,
        },
        "timing": {
            "sample_deadline": SAMPLE_DEADLINE,
            "sample_deadline_violations": observed_sample_violations,
            "sample_cycles_max": max(sample_maxima, default=0),
            "block_cycles_mean": int(stats.get("block_total_mean", "0")),
            "block_cycles_p95": int(stats.get("block_total_p95", "0")),
            "block_cycles_max": observed_block_max,
            "hard_block_budget": HARD_BLOCK_BUDGET,
            "block_deadline_violations": observed_block_violations,
            "target_block_budget": TARGET_BLOCK_BUDGET,
            "hard_budget_utilization": (
                observed_block_max / HARD_BLOCK_BUDGET
                if HARD_BLOCK_BUDGET else None
            ),
            "realtime_verdict": realtime_verdict,
        },
        "signal_metrics": {
            "input_snr_db": input_snr,
            "output_snr_db": output_snr,
            "snr_improvement_db": (
                output_snr - input_snr
                if output_snr is not None and input_snr is not None else None
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log_path", type=Path)
    parser.add_argument("--scenario", type=int)
    parser.add_argument("--algorithm", type=int)
    parser.add_argument("--search-mode", type=int, choices=(0, 1))
    parser.add_argument("--implementation", default="0.4.1")
    parser.add_argument("--firmware-revision", type=int, default=17)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(
        args.log_path,
        expected_scenario=args.scenario,
        expected_algorithm=args.algorithm,
        expected_search_mode=args.search_mode,
        expected_implementation=args.implementation,
        expected_firmware_revision=args.firmware_revision,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes((payload + "\n").encode("utf-8"))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
