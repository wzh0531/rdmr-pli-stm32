"""Build the C generator and verify Phase-1 pointwise alignment."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np

from signal_protocol import alignment_configs, generate_signal, load_protocol


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "outputs" / "phase1_alignment"
C_SOURCE = ROOT / "firmware" / "host_test" / "dump_signal_alignment.c"
C_PROTOCOL = ROOT / "firmware" / "core" / "rdmr_signal_protocol.c"
C_EXE = OUTPUT_DIR / "dump_signal_alignment.exe"
C_CSV = OUTPUT_DIR / "c_alignment_vectors.csv"
PYTHON_CSV = OUTPUT_DIR / "python_alignment_vectors.csv"
REPORT = OUTPUT_DIR / "alignment_report.json"
FIELDS = (
    "scenario_id",
    "seed",
    "n",
    "clean",
    "interference",
    "noise",
    "input",
    "true_frequency_hz",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_and_run_c() -> None:
    compiler = shutil.which("gcc")
    if compiler is None:
        raise RuntimeError("gcc is required for host/C alignment verification")
    subprocess.run(
        [
            compiler,
            "-std=c99",
            "-O2",
            "-Wall",
            "-Wextra",
            str(C_SOURCE),
            str(C_PROTOCOL),
            str(ROOT / "firmware" / "core" / "rdmr_trig.c"),
            "-I",
            str(ROOT / "firmware" / "core"),
            "-lm",
            "-o",
            str(C_EXE),
        ],
        check=True,
    )
    result = subprocess.run(
        [str(C_EXE)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    C_CSV.write_text(result.stdout, encoding="utf-8", newline="")


def _write_python_vectors() -> None:
    contract = load_protocol()
    indices = [int(value) for value in contract["alignment_sample_indices"]]
    with PYTHON_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for scenario_id, config in alignment_configs():
            arrays = generate_signal(config)
            for index in indices:
                writer.writerow(
                    {
                        "scenario_id": scenario_id,
                        "seed": config.seed,
                        "n": index,
                        "clean": format(float(arrays.clean[index]), ".9g"),
                        "interference": format(
                            float(arrays.interference[index]),
                            ".9g",
                        ),
                        "noise": format(float(arrays.noise[index]), ".9g"),
                        "input": format(float(arrays.input[index]), ".9g"),
                        "true_frequency_hz": format(
                            float(arrays.true_frequency_hz[index]),
                            ".9g",
                        ),
                    }
                )


def _read_rows(path: Path) -> dict[tuple[str, int, int], dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        (row["scenario_id"], int(row["seed"]), int(row["n"])): row
        for row in rows
    }


def _compare() -> dict[str, object]:
    c_rows = _read_rows(C_CSV)
    python_rows = _read_rows(PYTHON_CSV)
    if c_rows.keys() != python_rows.keys():
        missing_c = sorted(python_rows.keys() - c_rows.keys())
        missing_python = sorted(c_rows.keys() - python_rows.keys())
        raise AssertionError(
            f"row-key mismatch: missing_c={missing_c}, "
            f"missing_python={missing_python}"
        )

    tolerances = {
        "clean": 2.0e-6,
        "interference": 2.0e-6,
        "noise": 2.0e-6,
        "input": 3.0e-6,
        "true_frequency_hz": 1.0e-7,
    }
    maxima = {field: 0.0 for field in tolerances}
    failures: list[dict[str, object]] = []
    for key in sorted(c_rows):
        for field, tolerance in tolerances.items():
            difference = abs(
                float(c_rows[key][field]) - float(python_rows[key][field])
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
    return {
        "status": "PASS" if not failures else "FAIL",
        "row_count": len(c_rows),
        "tolerances": tolerances,
        "maximum_absolute_differences": maxima,
        "failures": failures,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _build_and_run_c()
    _write_python_vectors()
    report = _compare()
    report.update(
        {
            "protocol_id": load_protocol()["protocol_id"],
            "development_seeds": [0, 1, 2, 3, 4],
            "c_vectors_sha256": _sha256(C_CSV),
            "python_vectors_sha256": _sha256(PYTHON_CSV),
            "artifact_hashes": {
                "machine_config": _sha256(
                    ROOT
                    / "config"
                    / "experiment_protocol__rdmr-pli__v0.3.0.json"
                ),
                "c_config_header": _sha256(
                    ROOT / "firmware" / "core" / "rdmr_experiment_config.h"
                ),
                "c_signal_header": _sha256(
                    ROOT / "firmware" / "core" / "rdmr_signal_protocol.h"
                ),
                "c_signal_generator": _sha256(C_PROTOCOL),
                "python_signal_generator": _sha256(
                    Path(__file__).resolve().parent / "signal_protocol.py"
                ),
                "stm32_main": _sha256(
                    ROOT / "firmware" / "stm32_keil" / "App" / "main.c"
                ),
                "stm32_hex": _sha256(
                    ROOT
                    / "firmware"
                    / "stm32_keil"
                    / "build"
                    / "rdmr_stm32.hex"
                ),
                "stm32_map": _sha256(
                    ROOT
                    / "firmware"
                    / "stm32_keil"
                    / "build"
                    / "rdmr_stm32.map"
                ),
            },
        }
    )
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
