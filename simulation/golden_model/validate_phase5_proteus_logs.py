"""Validate received Phase-5 Proteus UART logs against the firmware manifest."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "outputs" / "phase5_proteus_core"
MANIFEST = BASE / "phase5_proteus_core_firmware_manifest.json"
LOGS = BASE / "logs"
REPORT = BASE / "phase5_proteus_log_validation.json"
HEADER = [
    "run_id", "scenario_id", "algorithm", "seed", "n", "input",
    "clean", "output", "true_frequency", "estimated_frequency",
    "estimated_frequency_next", "tracker_calls", "state", "cycles",
    "block_cycles_mean", "block_cycles_p95", "residual_ratio",
    "desired_energy", "input_error_energy", "output_error_energy",
    "numeric_flags",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes())
    return digest.hexdigest().upper()


def key_values(line: str) -> dict[str, str]:
    values = {}
    for item in line.split(",")[1:]:
        if "=" in item:
            key, value = item.split("=", 1)
            values[key] = value
    return values


def validate(path: Path, expected: dict[str, object]) -> dict[str, object]:
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        if line.strip()
    ]
    errors: list[str] = []
    realtime_errors: list[str] = []
    boot = next((line for line in lines if line.startswith("BOOT,")), "")
    config_line = next((line for line in lines if line.startswith("CONFIG,")), "")
    stats_line = next((line for line in lines if line.startswith("STATS,")), "")
    done_line = next((line for line in lines if line.startswith("DONE,")), "")
    header_index = next(
        (index for index, line in enumerate(lines) if line == ",".join(HEADER)),
        None,
    )
    if not boot:
        errors.append("missing BOOT")
    if "implementation=0.3.2" not in boot or "firmware_revision=14" not in boot:
        errors.append("BOOT version/revision mismatch")
    if not config_line:
        errors.append("missing CONFIG")
    config = key_values(config_line) if config_line else {}
    expected_config = {
        "scenario_id": expected["scenario_id"],
        "algorithm": expected["algorithm_id"],
        "trajectory": expected["trajectory_id"],
        "noise": expected["noise_id"],
        "near_line": expected["near_line_id"],
        "seed": expected["seed"],
        "sample_count": expected["expected_sample_count"],
        "pli_amplitude_u6": expected["pli_amplitude_u6"],
    }
    for key, value in expected_config.items():
        if config.get(key) != str(value):
            errors.append(f"CONFIG {key}: {config.get(key)} != {value}")
    if header_index is None:
        errors.append("missing/exact CSV header mismatch")
        data_rows = []
    else:
        data_lines = []
        for line in lines[header_index + 1:]:
            if line.startswith(("STATS,", "DONE,", "ERROR,")):
                break
            if line[:1].isdigit():
                data_lines.append(line)
        data_rows = list(csv.DictReader(
            io.StringIO("\n".join([",".join(HEADER), *data_lines]))
        ))
    if len(data_rows) != 160:
        errors.append(f"data rows {len(data_rows)} != 160")
    expected_n = list(range(50, 8001, 50))
    try:
        observed_n = [int(row["n"]) for row in data_rows]
        if observed_n != expected_n:
            errors.append("n sequence mismatch")
        if any(int(row["numeric_flags"]) != 0 for row in data_rows):
            errors.append("numeric_flags nonzero")
        if any(int(row["cycles"]) >= 72000 for row in data_rows):
            realtime_errors.append("block maximum cycle deadline violation")
        calls = [int(row["tracker_calls"]) for row in data_rows]
        states = [int(row["state"]) for row in data_rows]
        algorithm = int(expected["algorithm_id"])
        if algorithm < 2 and (any(calls) or any(state != 3 for state in states)):
            errors.append("A0/A1 tracker/state mismatch")
        if algorithm == 2 and (calls[-1] != 160 or any(state != 0 for state in states)):
            errors.append("A2 tracker/state mismatch")
        if algorithm == 3 and (
            not (0 < calls[-1] < 160)
            or any(state not in (0, 1, 2) for state in states)
        ):
            errors.append("A3 tracker/state mismatch")
    except (KeyError, TypeError, ValueError, IndexError) as error:
        errors.append(f"data parse failure: {error}")
    stats = key_values(stats_line) if stats_line else {}
    done = key_values(done_line) if done_line else {}
    if not stats_line:
        errors.append("missing STATS")
    if stats.get("cycles_count") != "8000":
        errors.append("STATS cycles_count mismatch")
    if stats.get("deadline_violations") != "0":
        realtime_errors.append("STATS deadline violations")
    if stats.get("numeric_faults") != "0":
        errors.append("STATS numeric faults")
    if not done_line or done.get("rows") != "160" or done.get("status") != "PASS":
        errors.append("DONE mismatch")
    return {
        "scenario_id": expected["scenario_id"],
        "log": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "status": (
            "PASS" if not errors and not realtime_errors
            else ("FAIL_REALTIME" if not errors else "FAIL_INTEGRITY")
        ),
        "integrity_status": "PASS" if not errors else "FAIL",
        "realtime_status": "PASS" if not realtime_errors else "FAIL",
        "row_count": len(data_rows),
        "cycles_mean": int(stats["cycles_mean"]) if stats.get("cycles_mean", "").isdigit() else None,
        "cycles_p95": int(stats["cycles_p95"]) if stats.get("cycles_p95", "").isdigit() else None,
        "cycles_max": int(stats["cycles_max"]) if stats.get("cycles_max", "").isdigit() else None,
        "tracker_cycles_mean": (
            int(stats["tracker_cycles_mean"])
            if stats.get("tracker_cycles_mean", "").isdigit() else None
        ),
        "final_tracker_calls": (
            int(data_rows[-1]["tracker_calls"]) if data_rows else None
        ),
        "errors": errors,
        "realtime_errors": realtime_errors,
    }


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    results = []
    missing = []
    for expected in manifest["scenarios"]:
        path = LOGS / expected["log_filename"]
        if path.is_file():
            results.append(validate(path, expected))
        else:
            missing.append(expected["log_filename"])
    integrity_failures = [
        result for result in results
        if result["integrity_status"] == "FAIL"
    ]
    realtime_failures = [
        result for result in results
        if result["realtime_status"] == "FAIL"
    ]
    status = (
        "FAIL_INTEGRITY" if integrity_failures
        else (
            "FAIL_REALTIME" if len(results) == 12 and realtime_failures
            else (
                "WAITING_WITH_REALTIME_FAILURE"
                if missing and realtime_failures else (
                    "WAITING" if missing else "PASS"
                )
            )
        )
    )
    report = {
        "schema_version": "1.0.0",
        "status": status,
        "received": len(results),
        "expected": 12,
        "missing": missing,
        "integrity_failures": integrity_failures,
        "realtime_failures": realtime_failures,
        "results": results,
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if integrity_failures or (len(results) == 12 and realtime_failures):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
