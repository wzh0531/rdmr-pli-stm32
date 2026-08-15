"""Build and smoke-test exhaustive versus hierarchical tracker searches.

This script is the Phase-8 bridge check.  It never rewrites Phase-4 inputs or
metrics.  The exhaustive build must reproduce frozen A2/A3 arrays exactly;
the hierarchical build is then evaluated on the same paired inputs.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "firmware" / "core"
RUNNER = ROOT / "firmware" / "host_test" / "tracker_optimization_runner.c"
BATCHES = ROOT / "outputs" / "phase4_host" / "batches"
OUT = ROOT / "outputs" / "phase8_realtime_strengthening" / "host_bridge"
ALGORITHMS = {2: "A2", 3: "A3", 7: "B4"}
SELECTED_ARCHIVES = (
    "main_F0_P050_Z0_N0.npz",
    "main_F1_P050_Z1_N0.npz",
    "main_F2_P020_Z1_N0.npz",
    "main_F3_P050_Z0_N0.npz",
    "main_F4_P020_Z0_N0.npz",
    "main_F5_P100_Z2_N0.npz",
)
SELECTED_SEED_INDICES = (0, 14, 29)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def build_library(search_mode: int) -> Path:
    compiler = shutil.which("gcc")
    if compiler is None:
        raise RuntimeError("gcc is required for the Phase-8 host bridge")
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / (
        "tracker_hierarchical.dll" if search_mode else "tracker_exhaustive.dll"
    )
    sources = [
        RUNNER,
        CORE / "rdmr_algorithm.c",
        CORE / "rdmr_pli.c",
        CORE / "rdmr_trig.c",
    ]
    command = [
        compiler,
        "-std=c99",
        "-O2",
        "-Wall",
        "-Wextra",
        "-shared",
        *(str(path.relative_to(ROOT)) for path in sources),
        "-I",
        str(CORE.relative_to(ROOT)),
        f"-DRDMR_TRACKER_SEARCH_MODE={search_mode}",
        "-lm",
        "-o",
        str(output.relative_to(ROOT)),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return output


def load_library(path: Path):
    library = ctypes.CDLL(str(path))
    f32 = np.ctypeslib.ndpointer(np.float32, flags="C_CONTIGUOUS")
    u32 = np.ctypeslib.ndpointer(np.uint32, flags="C_CONTIGUOUS")
    u8 = np.ctypeslib.ndpointer(np.uint8, flags="C_CONTIGUOUS")
    library.optimization_run_external.argtypes = [
        ctypes.c_int,
        ctypes.c_uint32,
        f32,
        f32,
        f32,
        f32,
        u32,
        u32,
        u32,
        u8,
    ]
    library.optimization_run_external.restype = ctypes.c_int
    library.optimization_tracker_search_mode.restype = ctypes.c_uint32
    library.optimization_tracker_max_grid_evaluations.restype = ctypes.c_uint32
    return library


def run_external(library, algorithm: int, values: np.ndarray):
    input_values = np.ascontiguousarray(values, dtype=np.float32)
    output = np.empty(input_values.size, np.float32)
    estimated = np.empty(input_values.size, np.float32)
    residual = np.empty(input_values.size, np.float32)
    calls = np.empty(input_values.size, np.uint32)
    searches = np.empty(input_values.size, np.uint32)
    evaluations = np.empty(input_values.size, np.uint32)
    state = np.empty(input_values.size, np.uint8)
    code = library.optimization_run_external(
        algorithm,
        input_values.size,
        input_values,
        output,
        estimated,
        residual,
        calls,
        searches,
        evaluations,
        state,
    )
    if code != 1:
        raise RuntimeError(f"host runner failed: algorithm={algorithm}, code={code}")
    return {
        "output": output,
        "estimated_frequency": estimated,
        "residual_ratio": residual,
        "tracker_calls": calls,
        "tracker_searches": searches,
        "tracker_grid_evaluations": evaluations,
        "state": state,
    }


def finite_arrays(result: dict[str, np.ndarray]) -> bool:
    return all(
        np.isfinite(values).all()
        for key, values in result.items()
        if key in {"output", "estimated_frequency", "residual_ratio"}
    )


def main() -> None:
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full",
        action="store_true",
        help="run all 54 frozen conditions and all 30 seeds",
    )
    args = parser.parse_args()
    if args.full:
        OUT = (
            ROOT
            / "outputs"
            / "phase8_realtime_strengthening"
            / "host_bridge_full"
        )
        archive_names = tuple(path.name for path in sorted(BATCHES.glob("main_*.npz")))
        seed_indices = tuple(range(30))
    else:
        archive_names = SELECTED_ARCHIVES
        seed_indices = SELECTED_SEED_INDICES

    exhaustive_path = build_library(0)
    hierarchical_path = build_library(1)
    libraries = {
        0: load_library(exhaustive_path),
        1: load_library(hierarchical_path),
    }
    for mode, library in libraries.items():
        if int(library.optimization_tracker_search_mode()) != mode:
            raise RuntimeError(f"search mode metadata mismatch for mode {mode}")

    rows = []
    regression_mismatches = []
    invalid_evaluation_counts = []
    nonfinite_runs = []
    for archive_name in archive_names:
        archive = np.load(BATCHES / archive_name)
        metadata = json.loads(str(archive["metadata_json"]))
        for seed_index in seed_indices:
            clean = archive["clean"][seed_index].astype(np.float64)
            input_values = archive["input"][seed_index]
            true_frequency = archive["true_frequency"][seed_index].astype(np.float64)
            desired_energy = float(np.dot(clean, clean))
            paired_results = {}
            for algorithm in ALGORITHMS:
                for mode, library in libraries.items():
                    result = run_external(library, algorithm, input_values)
                    paired_results[(algorithm, mode)] = result
                    if not finite_arrays(result):
                        nonfinite_runs.append(
                            {"archive": archive_name, "seed_index": seed_index,
                             "algorithm": algorithm, "search_mode": mode}
                        )
                    searches = int(result["tracker_searches"][-1])
                    evaluations = int(result["tracker_grid_evaluations"][-1])
                    expected_per_search = 201 if mode == 0 else 32
                    if evaluations != searches * expected_per_search:
                        invalid_evaluation_counts.append(
                            {"archive": archive_name, "seed_index": seed_index,
                             "algorithm": algorithm, "search_mode": mode,
                             "searches": searches, "evaluations": evaluations,
                             "expected": searches * expected_per_search}
                        )
                    error = result["output"].astype(np.float64) - clean
                    rows.append({
                        "archive": archive_name,
                        "trajectory": metadata["trajectory"],
                        "pli_amplitude": float(metadata["pli_amplitude"]),
                        "noise": int(metadata["noise"]),
                        "seed": int(metadata["seeds"][seed_index]),
                        "algorithm": algorithm,
                        "algorithm_name": ALGORITHMS[algorithm],
                        "search_mode": mode,
                        "output_snr_db": 10.0 * math.log10(
                            desired_energy / float(np.dot(error, error))
                        ),
                        "frequency_mae_hz": float(np.mean(np.abs(
                            result["estimated_frequency"].astype(np.float64)
                            - true_frequency
                        ))),
                        "rmse": float(np.sqrt(np.mean(error * error))),
                        "tracker_calls": int(result["tracker_calls"][-1]),
                        "tracker_searches": searches,
                        "tracker_grid_evaluations": evaluations,
                    })

                if algorithm in (2, 3):
                    exhaustive = paired_results[(algorithm, 0)]
                    expected_fields = {
                        "output": archive["output"][algorithm, seed_index],
                        "estimated_frequency": archive["estimated_frequency"][algorithm, seed_index],
                        "residual_ratio": archive["residual_ratio"][algorithm, seed_index],
                        "tracker_calls": archive["tracker_calls"][algorithm, seed_index],
                        "state": archive["state"][algorithm, seed_index],
                    }
                    for field, expected in expected_fields.items():
                        if not np.array_equal(exhaustive[field], expected):
                            regression_mismatches.append(
                                {"archive": archive_name, "seed_index": seed_index,
                                 "algorithm": algorithm, "field": field}
                            )

    metrics_path = OUT / "tracker_bridge_metrics.csv"
    with metrics_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    indexed = {
        (row["archive"], row["seed"], row["algorithm"], row["search_mode"]): row
        for row in rows
    }
    differences = []
    for key, hierarchical in indexed.items():
        if key[-1] != 1:
            continue
        exhaustive = indexed[key[:-1] + (0,)]
        differences.append({
            "archive": key[0],
            "seed": key[1],
            "algorithm": key[2],
            "snr_difference_db": (
                hierarchical["output_snr_db"] - exhaustive["output_snr_db"]
            ),
            "frequency_mae_difference_hz": (
                hierarchical["frequency_mae_hz"]
                - exhaustive["frequency_mae_hz"]
            ),
            "call_difference": (
                hierarchical["tracker_calls"] - exhaustive["tracker_calls"]
            ),
            "evaluation_reduction_fraction": 1.0 - (
                hierarchical["tracker_grid_evaluations"]
                / exhaustive["tracker_grid_evaluations"]
            ),
        })
    difference_path = OUT / "tracker_bridge_differences.csv"
    with difference_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(differences[0]))
        writer.writeheader()
        writer.writerows(differences)

    snr_differences = np.asarray([row["snr_difference_db"] for row in differences])
    mae_differences = np.asarray([
        row["frequency_mae_difference_hz"] for row in differences
    ])
    reductions = np.asarray([
        row["evaluation_reduction_fraction"] for row in differences
    ])
    status = "PASS" if not (
        regression_mismatches
        or invalid_evaluation_counts
        or nonfinite_runs
    ) else "FAIL"
    summary = {
        "status": status,
        "scope": (
            "Phase-8 full 54-condition frozen bridge"
            if args.full
            else "Phase-8 smoke bridge; not the full 54-condition science gate"
        ),
        "archives": list(archive_names),
        "seed_indices": list(seed_indices),
        "paired_mode_comparisons": len(differences),
        "exhaustive_regression_mismatches": regression_mismatches,
        "invalid_evaluation_counts": invalid_evaluation_counts,
        "nonfinite_runs": nonfinite_runs,
        "hierarchical_minus_exhaustive": {
            "mean_output_snr_db": float(snr_differences.mean()),
            "minimum_output_snr_db": float(snr_differences.min()),
            "mean_frequency_mae_hz": float(mae_differences.mean()),
            "maximum_frequency_mae_hz": float(mae_differences.max()),
            "mean_grid_evaluation_reduction_fraction": float(reductions.mean()),
            "minimum_grid_evaluation_reduction_fraction": float(reductions.min()),
        },
        "search_metadata": {
            "exhaustive_max_grid_evaluations": int(
                libraries[0].optimization_tracker_max_grid_evaluations()
            ),
            "hierarchical_max_grid_evaluations": int(
                libraries[1].optimization_tracker_max_grid_evaluations()
            ),
        },
    }
    summary_path = OUT / "tracker_bridge_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "1.0.0",
        "protocol": "rdmr-pli-realtime-strengthening-v0.5.0",
        "status": status,
        "files": {
            str(path.relative_to(ROOT)): sha256(path)
            for path in (
                exhaustive_path,
                hierarchical_path,
                metrics_path,
                difference_path,
                summary_path,
            )
        },
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
