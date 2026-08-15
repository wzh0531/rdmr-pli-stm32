"""Verify the formal float32 Python path against the shared C algorithms."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np

from formal_algorithms import run_formal_algorithm
from signal_protocol import ExperimentConfig, generate_signal


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "outputs" / "phase2_acceptance"
C_CSV = OUTPUT_DIR / "c_algorithm_alignment.csv"
PYTHON_CSV = OUTPUT_DIR / "python_algorithm_alignment.csv"
REPORT = OUTPUT_DIR / "algorithm_alignment_report.json"
SAMPLE_COUNT = 4202
FIELDS = (
    "algorithm",
    "n",
    "input",
    "output",
    "frequency_used_hz",
    "frequency_next_hz",
    "tracker_calls",
    "state_used",
    "state_next",
    "residual_ratio",
)


def should_emit(index: int) -> bool:
    return (
        index % 50 == 49
        or index in {0, 1, 2, 3998, 3999, 4000, 4001, 4201}
    )


def build_and_run_c() -> None:
    compiler = shutil.which("gcc")
    if compiler is None:
        raise RuntimeError("gcc is required for algorithm alignment")
    core = ROOT / "firmware" / "core"
    source = ROOT / "firmware" / "host_test" / "dump_algorithm_alignment.c"
    with tempfile.TemporaryDirectory(prefix="rdmr-alignment-") as temp_dir:
        executable = Path(temp_dir) / "dump_algorithm_alignment.exe"
        subprocess.run(
            [
                compiler,
                "-std=c99",
                "-O2",
                "-Wall",
                "-Wextra",
                str(source),
                str(core / "rdmr_algorithm.c"),
                str(core / "rdmr_pli.c"),
                str(core / "rdmr_signal_protocol.c"),
                str(core / "rdmr_trig.c"),
                "-I",
                str(core),
                "-lm",
                "-o",
                str(executable),
            ],
            check=True,
        )
        result = subprocess.run(
            [str(executable)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    C_CSV.write_text(result.stdout, encoding="utf-8", newline="")


def write_python_rows() -> None:
    config = ExperimentConfig(
        algorithm="A3",
        trajectory="F1",
        pli_amplitude=0.50,
        noise="snr_20_db",
        near_line="N0",
        seed=0,
        sample_count=SAMPLE_COUNT,
    )
    signals = generate_signal(config)
    with PYTHON_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for algorithm_id in range(4):
            result = run_formal_algorithm(signals.input, algorithm_id)
            for index in range(SAMPLE_COUNT):
                if not should_emit(index):
                    continue
                writer.writerow(
                    {
                        "algorithm": algorithm_id,
                        "n": index,
                        "input": format(float(signals.input[index]), ".9g"),
                        "output": format(float(result.output[index]), ".9g"),
                        "frequency_used_hz": format(
                            float(result.frequency_used_hz[index]),
                            ".9g",
                        ),
                        "frequency_next_hz": format(
                            float(result.frequency_next_hz[index]),
                            ".9g",
                        ),
                        "tracker_calls": int(result.tracker_calls[index]),
                        "state_used": int(result.state_used[index]),
                        "state_next": int(result.state_next[index]),
                        "residual_ratio": format(
                            float(result.residual_ratio[index]),
                            ".9g",
                        ),
                    }
                )


def read_rows(path: Path) -> dict[tuple[int, int], dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        (int(row["algorithm"]), int(row["n"])): row
        for row in rows
    }


def compare() -> dict[str, object]:
    c_rows = read_rows(C_CSV)
    py_rows = read_rows(PYTHON_CSV)
    if c_rows.keys() != py_rows.keys():
        raise AssertionError("C/Python algorithm row keys differ")
    tolerances = {
        "input": 3.0e-6,
        "output": 2.0e-4,
        "frequency_used_hz": 5.0e-4,
        "frequency_next_hz": 5.0e-4,
        "residual_ratio": 2.0e-5,
    }
    exact_fields = ("tracker_calls", "state_used", "state_next")
    maxima = {field: 0.0 for field in tolerances}
    failures: list[dict[str, object]] = []
    for key in sorted(c_rows):
        for field, tolerance in tolerances.items():
            difference = abs(
                float(c_rows[key][field]) - float(py_rows[key][field])
            )
            maxima[field] = max(maxima[field], difference)
            if not np.isfinite(difference) or difference > tolerance:
                failures.append(
                    {
                        "key": key,
                        "field": field,
                        "difference": difference,
                        "tolerance": tolerance,
                    }
                )
        for field in exact_fields:
            if int(c_rows[key][field]) != int(py_rows[key][field]):
                failures.append(
                    {
                        "key": key,
                        "field": field,
                        "c": c_rows[key][field],
                        "python": py_rows[key][field],
                    }
                )
    return {
        "status": "PASS" if not failures else "FAIL",
        "row_count": len(c_rows),
        "scenario": "F1, amplitude=0.50, noise=20 dB, seed=0",
        "sample_count_processed_per_algorithm": SAMPLE_COUNT,
        "tolerances": tolerances,
        "maximum_absolute_differences": maxima,
        "failures": failures[:100],
        "failure_count": len(failures),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    build_and_run_c()
    write_python_rows()
    report = compare()
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
