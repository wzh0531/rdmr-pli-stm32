"""Audit available Phase-5 P2 A2/A3 amplitude pairs against the frozen host path."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

import run_phase4_host_matrix as phase4


ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "outputs" / "phase5_proteus_core" / "logs"
REPORT = (
    ROOT / "outputs" / "phase5_proteus_core"
    / "phase5_p2_amplitude_pair_audit.json"
)
N = 8000
PAIR_SPECS = {
    "P020": {
        "amplitude": 0.20,
        2: (505, "PHASE5_P2_S505_A2_F2_P020_Z20_REV14.txt"),
        3: (506, "PHASE5_P2_S506_A3_F2_P020_Z20_REV14.txt"),
    },
    "P050": {
        "amplitude": 0.50,
        2: (507, "PHASE5_P2_S507_A2_F2_P050_Z20_REV14.txt"),
        3: (508, "PHASE5_P2_S508_A3_F2_P050_Z20_REV14.txt"),
    },
    "P100": {
        "amplitude": 1.00,
        2: (509, "PHASE5_P2_S509_A2_F2_P100_Z20_REV14.txt"),
        3: (510, "PHASE5_P2_S510_A3_F2_P100_Z20_REV14.txt"),
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def parse_log(path: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    header_index = next(
        index for index, line in enumerate(lines)
        if line.startswith("run_id,scenario_id,")
    )
    data = [
        line for line in lines[header_index + 1:]
        if line[:1].isdigit()
    ]
    rows = list(csv.DictReader([lines[header_index], *data]))
    stats_line = next(line for line in lines if line.startswith("STATS,"))
    stats = {
        item.split("=", 1)[0]: item.split("=", 1)[1]
        for item in stats_line.split(",")[1:]
    }
    return rows, stats


def host_run(
    library: object,
    algorithm: int,
    amplitude: float,
) -> dict[str, np.ndarray]:
    arrays = {
        "input": np.empty(N, np.float32),
        "clean": np.empty(N, np.float32),
        "output": np.empty(N, np.float32),
        "true": np.empty(N, np.float32),
        "estimated": np.empty(N, np.float32),
        "residual": np.empty(N, np.float32),
        "calls": np.empty(N, np.uint32),
        "state": np.empty(N, np.uint8),
    }
    code = library.phase4_run(
        algorithm, 2, 0, 1, 20260727, amplitude, N,
        arrays["input"], arrays["clean"], arrays["output"],
        arrays["true"], arrays["estimated"], arrays["residual"],
        arrays["calls"], arrays["state"],
    )
    if code != 1:
        raise RuntimeError(
            f"host reference failed for A{algorithm}, amplitude={amplitude}"
        )
    return arrays


def analyze_one(
    path: Path,
    scenario_id: int,
    algorithm: int,
    rows: list[dict[str, str]],
    stats: dict[str, str],
    host: dict[str, np.ndarray],
) -> dict[str, object]:
    indices = np.arange(49, N, 50)
    desired = sum(int(row["desired_energy"]) for row in rows)
    output_error = sum(int(row["output_error_energy"]) for row in rows)
    proteus_snr = 10.0 * math.log10(desired / output_error)
    host_error = host["output"].astype(np.float64) - host["clean"]
    host_snr = 10.0 * math.log10(
        float(np.dot(host["clean"].astype(np.float64), host["clean"]))
        / float(np.dot(host_error, host_error))
    )
    log_frequency = np.asarray(
        [int(row["estimated_frequency"]) / 1000.0 for row in rows]
    )
    log_true = np.asarray(
        [int(row["true_frequency"]) / 1000.0 for row in rows]
    )
    host_frequency_mae = float(np.mean(
        np.abs(host["estimated"][indices] - host["true"][indices])
    ))
    proteus_frequency_mae = float(np.mean(np.abs(log_frequency - log_true)))
    log_state = np.asarray([int(row["state"]) for row in rows])
    host_state = host["state"][indices]
    mismatch_indices = np.flatnonzero(log_state != host_state)
    log_calls = np.asarray([int(row["tracker_calls"]) for row in rows])
    return {
        "scenario_id": scenario_id,
        "algorithm": f"A{algorithm}",
        "log": str(path.relative_to(ROOT)),
        "log_sha256": sha256(path),
        "rows": len(rows),
        "proteus_output_snr_db": proteus_snr,
        "host_output_snr_db": host_snr,
        "output_snr_absolute_difference_db": abs(proteus_snr - host_snr),
        "proteus_endpoint_frequency_mae_hz": proteus_frequency_mae,
        "host_endpoint_frequency_mae_hz": host_frequency_mae,
        "frequency_mae_absolute_difference_hz": abs(
            proteus_frequency_mae - host_frequency_mae
        ),
        "proteus_final_tracker_calls": int(log_calls[-1]),
        "host_final_tracker_calls": int(host["calls"][-1]),
        "tracker_calls_absolute_difference": abs(
            int(log_calls[-1]) - int(host["calls"][-1])
        ),
        "endpoint_state_mismatches": int(mismatch_indices.size),
        "endpoint_state_mismatch_n": [
            int(rows[index]["n"]) for index in mismatch_indices
        ],
        "cycles_mean": int(stats["cycles_mean"]),
        "cycles_p95": int(stats["cycles_p95"]),
        "cycles_max": int(stats["cycles_max"]),
        "deadline_violations": int(stats["deadline_violations"]),
        "tracker_cycles_mean": int(stats["tracker_cycles_mean"]),
        "numeric_faults": int(stats["numeric_faults"]),
    }


def pair_gates(a2: dict[str, object], a3: dict[str, object]) -> dict[str, str]:
    state_mismatches = max(
        int(a2["endpoint_state_mismatches"]),
        int(a3["endpoint_state_mismatches"]),
    )
    return {
        "log_integrity": (
            "PASS" if a2["rows"] == 160 and a3["rows"] == 160 else "FAIL"
        ),
        "numeric_faults": (
            "PASS"
            if a2["numeric_faults"] == 0 and a3["numeric_faults"] == 0
            else "FAIL"
        ),
        "host_proteus_output_snr_le_0.10_db": (
            "PASS"
            if max(
                float(a2["output_snr_absolute_difference_db"]),
                float(a3["output_snr_absolute_difference_db"]),
            ) <= 0.10 else "FAIL"
        ),
        "host_proteus_endpoint_frequency_mae_le_0.05_hz": (
            "PASS"
            if max(
                float(a2["frequency_mae_absolute_difference_hz"]),
                float(a3["frequency_mae_absolute_difference_hz"]),
            ) <= 0.05 else "FAIL"
        ),
        "tracker_calls_difference_le_1": (
            "PASS"
            if max(
                int(a2["tracker_calls_absolute_difference"]),
                int(a3["tracker_calls_absolute_difference"]),
            ) <= 1 else "FAIL"
        ),
        "state_sequence": (
            "PASS" if state_mismatches == 0
            else f"WARN: up to {state_mismatches}/160 endpoint mismatches"
        ),
        "a3_mean_cycles_below_a2": (
            "PASS" if a3["cycles_mean"] < a2["cycles_mean"] else "FAIL"
        ),
        "maximum_sample_below_72000_cycles": (
            "PASS"
            if max(int(a2["cycles_max"]), int(a3["cycles_max"])) <= 72000
            else "FAIL"
        ),
        "zero_deadline_violations": (
            "PASS"
            if a2["deadline_violations"] == 0
            and a3["deadline_violations"] == 0
            else "FAIL"
        ),
    }


def main() -> None:
    library = phase4.load_runner()
    pairs = []
    missing = []
    for label, spec in PAIR_SPECS.items():
        paths = {
            algorithm: LOG_DIR / spec[algorithm][1]
            for algorithm in (2, 3)
        }
        missing.extend(
            str(path.relative_to(ROOT))
            for path in paths.values() if not path.exists()
        )
        if not all(path.exists() for path in paths.values()):
            continue
        analyses = {}
        for algorithm, path in paths.items():
            rows, stats = parse_log(path)
            analyses[algorithm] = analyze_one(
                path,
                int(spec[algorithm][0]),
                algorithm,
                rows,
                stats,
                host_run(library, algorithm, float(spec["amplitude"])),
            )
        a2 = analyses[2]
        a3 = analyses[3]
        pairs.append({
            "pair": label,
            "trajectory": "F2",
            "pli_amplitude": spec["amplitude"],
            "noise": 1,
            "near_line": 0,
            "seed": 20260727,
            "per_algorithm": [a2, a3],
            "a3_vs_a2": {
                "output_snr_difference_db": (
                    a3["proteus_output_snr_db"]
                    - a2["proteus_output_snr_db"]
                ),
                "mean_cycles_reduction_fraction": (
                    (a2["cycles_mean"] - a3["cycles_mean"])
                    / a2["cycles_mean"]
                ),
                "tracker_calls_reduction_fraction": (
                    (
                        a2["proteus_final_tracker_calls"]
                        - a3["proteus_final_tracker_calls"]
                    )
                    / a2["proteus_final_tracker_calls"]
                ),
                "deadline_violation_reduction_fraction": (
                    (
                        a2["deadline_violations"]
                        - a3["deadline_violations"]
                    )
                    / a2["deadline_violations"]
                ),
            },
            "gates": pair_gates(a2, a3),
        })
    realtime_failure = any(
        pair["gates"]["zero_deadline_violations"] == "FAIL"
        for pair in pairs
    )
    result = {
        "schema_version": "1.0.0",
        "status": (
            "WAITING_WITH_REALTIME_FAILURE"
            if missing and realtime_failure else (
                "WAITING" if missing else (
                    "FAIL_REALTIME" if realtime_failure else "PASS"
                )
            )
        ),
        "comparison": (
            "P2 A3 vs A2 amplitude sweep; F2, 20 dB, "
            "near-line N0, seed=20260727"
        ),
        "completed_pairs": len(pairs),
        "expected_pairs": len(PAIR_SPECS),
        "missing": missing,
        "pairs": pairs,
        "evidence_boundary": {
            "cycle_source": "Proteus simulated MCU DWT",
            "physical_mcu_measurement": False,
            "power_or_energy_measurement": False,
            "frozen_parameters_changed": False,
        },
    }
    REPORT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(error, file=sys.stderr)
        raise
