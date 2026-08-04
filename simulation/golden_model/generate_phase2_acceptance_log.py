"""Generate and validate a complete F1 host-reference log for Phase 2.

Cycle values are deliberately zero because this artifact validates the data
chain and schema, not DWT timing.  DWT measurements require Proteus or a
physical STM32 run and remain separately identified.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import numpy as np

from formal_algorithms import run_formal_algorithm
from signal_protocol import ExperimentConfig, generate_signal


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "outputs" / "phase2_acceptance"
LOG_PATH = OUTPUT_DIR / "f1_a3_host_reference_log.csv"
REPORT_PATH = OUTPUT_DIR / "f1_a3_log_validation.json"
EXECUTION_CONFIG_PATH = (
    ROOT / "config" / "firmware-execution__rdmr-pli__phase2__v0.3.1.json"
)
VALUE_SCALE = 1_000_000
FREQUENCY_SCALE = 1000
ENERGY_SCALE = 1_000_000
BLOCK_SIZE = 50
SAMPLE_COUNT = 8000


def scaled_i32(value: float, scale: int) -> tuple[int, int]:
    if not np.isfinite(value):
        return 0, 1
    scaled = value * scale
    if scaled > np.iinfo(np.int32).max:
        return int(np.iinfo(np.int32).max), 1
    if scaled < np.iinfo(np.int32).min:
        return int(np.iinfo(np.int32).min), 1
    return int(scaled), 0


def scaled_u32(value: float, scale: int) -> tuple[int, int]:
    if not np.isfinite(value) or value < 0.0:
        return 0, 1
    scaled = value * scale
    if scaled > np.iinfo(np.uint32).max:
        return int(np.iinfo(np.uint32).max), 1
    return int(scaled), 0


def accumulate_energy(values: np.ndarray) -> np.float32:
    total = np.float32(0.0)
    for value in values.astype(np.float32, copy=False):
        total = np.float32(total + np.float32(value * value))
    return total


def generate_log() -> None:
    execution = json.loads(EXECUTION_CONFIG_PATH.read_text(encoding="utf-8"))
    columns = list(execution["columns"])
    config = ExperimentConfig(
        algorithm="A3",
        trajectory="F1",
        pli_amplitude=0.50,
        noise="none",
        near_line="N0",
        seed=0,
        sample_count=SAMPLE_COUNT,
        log_schema_version=str(execution["log_schema_version"]),
    )
    signals = generate_signal(config)
    result = run_formal_algorithm(signals.input, 3)

    lines = [
        "BOOT,protocol=cssp-rdmr-pli-v0.3.0,"
        "implementation=0.3.1,schema=rdmr-block-csv-v2",
        "CONFIG,protocol=cssp-rdmr-pli-v0.3.0,"
        "implementation=0.3.1,schema=rdmr-block-csv-v2,"
        "run_id=1,scenario_id=101,algorithm=3,trajectory=1,noise=0,"
        "near_line=0,seed=0,fs_hz=1000,sample_count=8000,"
        "block_size=50,pli_amplitude_u6=500000,value_scale=1000000,"
        "frequency_scale=1000,cycles=block_max,"
        "measurement_route=host_reference_no_dwt",
    ]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    lines.extend(stream.getvalue().splitlines())

    numeric_faults = 0
    for block_start in range(0, SAMPLE_COUNT, BLOCK_SIZE):
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
        desired_energy = accumulate_energy(
            signals.clean[block_start:block_end]
        )
        input_error_energy = accumulate_energy(input_error)
        output_error_energy = accumulate_energy(output_error)

        flags = 0
        input_scaled, flag = scaled_i32(float(signals.input[index]), VALUE_SCALE)
        flags |= flag
        clean_scaled, flag = scaled_i32(float(signals.clean[index]), VALUE_SCALE)
        flags |= flag
        output_scaled, flag = scaled_i32(float(result.output[index]), VALUE_SCALE)
        flags |= flag
        true_frequency, flag = scaled_i32(
            float(signals.true_frequency_hz[index]),
            FREQUENCY_SCALE,
        )
        flags |= flag
        estimated_frequency, flag = scaled_i32(
            float(result.frequency_used_hz[index]),
            FREQUENCY_SCALE,
        )
        flags |= flag
        estimated_frequency_next, flag = scaled_i32(
            float(result.frequency_next_hz[index]),
            FREQUENCY_SCALE,
        )
        flags |= flag
        desired_scaled, flag = scaled_u32(
            float(desired_energy),
            ENERGY_SCALE,
        )
        flags |= flag
        input_energy_scaled, flag = scaled_u32(
            float(input_error_energy),
            ENERGY_SCALE,
        )
        flags |= flag
        output_energy_scaled, flag = scaled_u32(
            float(output_error_energy),
            ENERGY_SCALE,
        )
        flags |= flag
        if flags:
            numeric_faults += 1

        row = {
            "run_id": 1,
            "scenario_id": 101,
            "algorithm": 3,
            "seed": 0,
            "n": block_end,
            "input": input_scaled,
            "clean": clean_scaled,
            "output": output_scaled,
            "true_frequency": true_frequency,
            "estimated_frequency": estimated_frequency,
            "estimated_frequency_next": estimated_frequency_next,
            "tracker_calls": int(result.tracker_calls[index]),
            "state": int(result.state_next[index]),
            "cycles": 0,
            "block_cycles_mean": 0,
            "block_cycles_p95": 0,
            "residual_ratio": int(
                float(result.residual_ratio[index]) * VALUE_SCALE
            ),
            "desired_energy": desired_scaled,
            "input_error_energy": input_energy_scaled,
            "output_error_energy": output_energy_scaled,
            "numeric_flags": flags,
        }
        row_stream = io.StringIO()
        row_writer = csv.DictWriter(
            row_stream,
            fieldnames=columns,
            lineterminator="\n",
        )
        row_writer.writerow(row)
        lines.extend(row_stream.getvalue().splitlines())

    tracker_count = int(result.tracker_calls[-1])
    lines.append(
        "STATS,rows=160,cycles_count=8000,cycles_mean=0,"
        "cycles_median=0,cycles_p95=0,cycles_max=0,"
        "deadline_cycles=72000,deadline_violations=0,"
        f"tracker_cycle_count={tracker_count},tracker_cycles_mean=0,"
        "tracker_cycles_median=0,tracker_cycles_p95=0,"
        f"tracker_cycles_max=0,numeric_faults={numeric_faults},"
        "measurement_route=host_reference_no_dwt"
    )
    status = "PASS" if numeric_faults == 0 else "FAIL"
    lines.append(f"DONE,rows=160,status={status}")
    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_key_values(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in line.split(",")[1:]:
        key, value = item.split("=", 1)
        values[key] = value
    return values


def validate_log() -> dict[str, object]:
    execution = json.loads(EXECUTION_CONFIG_PATH.read_text(encoding="utf-8"))
    expected_columns = list(execution["columns"])
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    errors: list[str] = []
    if not lines or not lines[0].startswith("BOOT,"):
        errors.append("missing BOOT")
    if len(lines) < 5 or not lines[1].startswith("CONFIG,"):
        errors.append("missing CONFIG")
    if lines[2].split(",") != expected_columns:
        errors.append("header does not match execution config")
    if not lines[-2].startswith("STATS,"):
        errors.append("missing STATS")
    if not lines[-1].startswith("DONE,"):
        errors.append("missing DONE")

    data_lines = lines[3:-2]
    rows = list(csv.DictReader([lines[2], *data_lines]))
    if len(rows) != 160:
        errors.append(f"expected 160 data rows, got {len(rows)}")
    expected_n = list(range(50, 8001, 50))
    observed_n = [int(row["n"]) for row in rows]
    if observed_n != expected_n:
        errors.append("n is not the exact 50..8000 block sequence")
    if any(int(row["numeric_flags"]) != 0 for row in rows):
        errors.append("numeric_flags contains a nonzero value")
    if any(int(row["algorithm"]) != 3 for row in rows):
        errors.append("algorithm id drift")
    if any(int(row["seed"]) != 0 for row in rows):
        errors.append("seed drift")
    if any(int(row["tracker_calls"]) < 0 for row in rows):
        errors.append("negative tracker_calls")

    stats = parse_key_values(lines[-2]) if lines[-2].startswith("STATS,") else {}
    done = parse_key_values(lines[-1]) if lines[-1].startswith("DONE,") else {}
    if stats.get("rows") != "160":
        errors.append("STATS row count mismatch")
    if stats.get("numeric_faults") != "0":
        errors.append("STATS numeric fault count is nonzero")
    if done.get("rows") != "160" or done.get("status") != "PASS":
        errors.append("DONE marker is not PASS with 160 rows")
    return {
        "status": "PASS" if not errors else "FAIL",
        "artifact": str(LOG_PATH),
        "measurement_route": "host_reference_no_dwt",
        "data_rows": len(rows),
        "first_n": observed_n[0] if observed_n else None,
        "last_n": observed_n[-1] if observed_n else None,
        "tracker_calls_final": (
            int(rows[-1]["tracker_calls"]) if rows else None
        ),
        "numeric_fault_rows": sum(
            int(row["numeric_flags"]) != 0 for row in rows
        ),
        "errors": errors,
        "dwt_status": "NOT_CHECKED",
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_log()
    report = validate_log()
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
