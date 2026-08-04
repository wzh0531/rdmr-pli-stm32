"""Run the frozen 7920-run Phase-4 host matrix through the production C path."""

from __future__ import annotations

import csv
import ctypes
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "firmware" / "core"
SOURCE = ROOT / "firmware" / "host_test" / "phase4_matrix_runner.c"
FREEZE = (
    ROOT / "config"
    / "tuned-parameters__rdmr-pli__phase3__frozen__v1.0.0.json"
)
VERIFY = ROOT / "simulation" / "golden_model" / "verify_phase3_freeze.py"
OUT = ROOT / "outputs" / "phase4_host"
BATCH = OUT / "batches"
DLL = OUT / "phase4_matrix_runner.dll"
ROWS_CSV = OUT / "phase4_run_metrics.csv"
STATS_JSON = OUT / "phase4_paired_statistics.json"
MANIFEST = OUT / "phase4_completion_manifest.json"
N = 8000
SEEDS = range(1000, 1030)
TRAJECTORIES = range(6)
AMPLITUDES = (0.20, 0.50, 1.00)
NOISES = range(3)
NEAR_CASES = range(4)
BASIS = {
    frequency: np.exp(
        -2j * np.pi * frequency * np.arange(N, dtype=np.float64) / 1000.0
    )
    for frequency in (42.0, 58.0)
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def build_dll() -> None:
    compiler = shutil.which("gcc")
    if compiler is None:
        raise RuntimeError("gcc is required")
    command = [
        compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-shared",
        str(SOURCE.relative_to(ROOT)),
        str((CORE / "rdmr_algorithm.c").relative_to(ROOT)),
        str((CORE / "rdmr_pli.c").relative_to(ROOT)),
        str((CORE / "rdmr_signal_protocol.c").relative_to(ROOT)),
        str((CORE / "rdmr_trig.c").relative_to(ROOT)),
        "-I", str(CORE.relative_to(ROOT)), "-lm",
        "-o", str(DLL.relative_to(ROOT)),
    ]
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)


def load_runner() -> ctypes.CDLL:
    library = ctypes.CDLL(str(DLL))
    f32 = np.ctypeslib.ndpointer(np.float32, flags="C_CONTIGUOUS")
    u32 = np.ctypeslib.ndpointer(np.uint32, flags="C_CONTIGUOUS")
    u8 = np.ctypeslib.ndpointer(np.uint8, flags="C_CONTIGUOUS")
    library.phase4_run.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint32, ctypes.c_float, ctypes.c_uint32,
        f32, f32, f32, f32, f32, f32, u32, u8,
    ]
    library.phase4_run.restype = ctypes.c_int
    library.phase4_firmware_revision.restype = ctypes.c_uint32
    if library.phase4_firmware_revision() != 14:
        raise RuntimeError("Phase-4 runner is not firmware revision 14")
    return library


def spectral_component(values: np.ndarray, frequency: float) -> complex:
    return complex((2.0 / values.size) * np.dot(values, BASIS[frequency]))


def wrap_phase(value: float) -> float:
    return float((value + np.pi) % (2.0 * np.pi) - np.pi)


def metrics(
    matrix: str,
    trajectory: int,
    amplitude: float,
    noise: int,
    near: int,
    seed: int,
    algorithm: int,
    clean: np.ndarray,
    input_values: np.ndarray,
    output: np.ndarray,
    true_frequency: np.ndarray,
    estimated_frequency: np.ndarray,
    tracker: np.ndarray,
    state: np.ndarray,
    archive: Path,
    seed_index: int,
) -> dict[str, object]:
    desired = float(np.dot(clean.astype(np.float64), clean))
    input_error = input_values.astype(np.float64) - clean
    output_error = output.astype(np.float64) - clean
    input_energy = float(np.dot(input_error, input_error))
    output_energy = float(np.dot(output_error, output_error))
    frequency_error = np.abs(
        estimated_frequency.astype(np.float64) - true_frequency
    )
    transitions = int(np.count_nonzero(state[1:] != state[:-1]))
    row: dict[str, object] = {
        "run_id": (
            f"{matrix}-A{algorithm}-F{trajectory}-P{amplitude:.2f}-"
            f"Z{noise}-N{near}-S{seed}"
        ),
        "matrix": matrix, "algorithm": algorithm,
        "trajectory": f"F{trajectory}", "pli_amplitude": amplitude,
        "noise": noise, "near_line": f"N{near}", "seed": seed,
        "sample_count": N,
        "input_snr_db": 10.0 * math.log10(desired / input_energy),
        "output_snr_db": 10.0 * math.log10(desired / output_energy),
        "snr_improvement_db": 10.0 * math.log10(input_energy / output_energy),
        "rmse": math.sqrt(output_energy / N),
        "frequency_mae_hz": float(frequency_error.mean()),
        "frequency_p95_abs_error_hz": float(
            np.quantile(frequency_error, 0.95)
        ),
        "tracker_calls": int(tracker[-1]),
        "state_fast_fraction": float(np.mean(state == 0)),
        "state_mid_fraction": float(np.mean(state == 1)),
        "state_slow_fraction": float(np.mean(state == 2)),
        "state_transitions": transitions,
        "input_sha256": hashlib.sha256(input_values.tobytes()).hexdigest().upper(),
        "output_sha256": hashlib.sha256(output.tobytes()).hexdigest().upper(),
        "archive": str(archive.relative_to(ROOT)),
        "archive_algorithm_index": algorithm,
        "archive_seed_index": seed_index,
        "status": "PASS",
    }
    if matrix == "near":
        for frequency in (42.0, 58.0):
            clean_component = spectral_component(clean, frequency)
            output_component = spectral_component(output, frequency)
            row[f"f{int(frequency)}_clean_amplitude"] = abs(clean_component)
            row[f"f{int(frequency)}_output_amplitude"] = abs(output_component)
            row[f"f{int(frequency)}_amplitude_error"] = (
                abs(output_component) - abs(clean_component)
            )
            row[f"f{int(frequency)}_phase_error_rad"] = (
                wrap_phase(
                    np.angle(output_component) - np.angle(clean_component)
                )
                if abs(clean_component) > 1.0e-6 else ""
            )
    return row


def run_batch(
    library: ctypes.CDLL,
    matrix: str,
    trajectory: int,
    amplitude: float,
    noise: int,
    near: int,
) -> tuple[list[dict[str, object]], Path]:
    tag = (
        f"{matrix}_F{trajectory}_P{int(round(amplitude * 100)):03d}"
        f"_Z{noise}_N{near}"
    )
    archive = BATCH / f"{tag}.npz"
    shared = {
        name: np.empty((30, N), np.float32)
        for name in ("input", "clean", "true_frequency")
    }
    arrays = {
        name: np.empty((4, 30, N), dtype)
        for name, dtype in (
            ("output", np.float32), ("estimated_frequency", np.float32),
            ("residual_ratio", np.float32), ("tracker_calls", np.uint32),
            ("state", np.uint8),
        )
    }
    rows: list[dict[str, object]] = []
    scratch_input = np.empty(N, np.float32)
    scratch_clean = np.empty(N, np.float32)
    scratch_true = np.empty(N, np.float32)
    for seed_index, seed in enumerate(SEEDS):
        for algorithm in range(4):
            code = library.phase4_run(
                algorithm, trajectory, near, noise, seed, amplitude, N,
                scratch_input, scratch_clean, arrays["output"][algorithm, seed_index],
                scratch_true, arrays["estimated_frequency"][algorithm, seed_index],
                arrays["residual_ratio"][algorithm, seed_index],
                arrays["tracker_calls"][algorithm, seed_index],
                arrays["state"][algorithm, seed_index],
            )
            if code != 1:
                rows.append({
                    "run_id": f"{tag}-A{algorithm}-S{seed}",
                    "matrix": matrix, "algorithm": algorithm,
                    "trajectory": f"F{trajectory}", "pli_amplitude": amplitude,
                    "noise": noise, "near_line": f"N{near}", "seed": seed,
                    "sample_count": 0, "status": f"FAIL_C_CODE_{code}",
                    "archive": str(archive.relative_to(ROOT)),
                    "archive_algorithm_index": algorithm,
                    "archive_seed_index": seed_index,
                })
                continue
            if algorithm == 0:
                shared["input"][seed_index] = scratch_input
                shared["clean"][seed_index] = scratch_clean
                shared["true_frequency"][seed_index] = scratch_true
            elif not (
                np.array_equal(shared["input"][seed_index], scratch_input)
                and np.array_equal(shared["clean"][seed_index], scratch_clean)
                and np.array_equal(shared["true_frequency"][seed_index], scratch_true)
            ):
                raise RuntimeError(f"input pairing failed: {tag}, seed={seed}")
            rows.append(metrics(
                matrix, trajectory, amplitude, noise, near, seed, algorithm,
                shared["clean"][seed_index], shared["input"][seed_index],
                arrays["output"][algorithm, seed_index],
                shared["true_frequency"][seed_index],
                arrays["estimated_frequency"][algorithm, seed_index],
                arrays["tracker_calls"][algorithm, seed_index],
                arrays["state"][algorithm, seed_index],
                archive, seed_index,
            ))
    np.savez_compressed(
        archive, **shared, **arrays,
        metadata_json=np.asarray(json.dumps({
            "matrix": matrix, "trajectory": f"F{trajectory}",
            "pli_amplitude": amplitude, "noise": noise,
            "near_line": f"N{near}", "seeds": list(SEEDS),
            "algorithms": [0, 1, 2, 3], "sample_count": N,
            "freeze_manifest_sha256": sha256(FREEZE),
        })),
    )
    return rows, archive


def bootstrap_ci(values: np.ndarray, seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, values.size, size=(20000, values.size))
    means = values[indices].mean(axis=1)
    return [float(value) for value in np.quantile(means, [0.025, 0.975])]


def paired_statistics(rows: list[dict[str, object]]) -> dict[str, object]:
    main = [row for row in rows if row["matrix"] == "main"]
    indexed = {
        (row["trajectory"], row["pli_amplitude"], row["noise"], row["seed"], row["algorithm"]): row
        for row in main
    }
    differences = []
    reductions = []
    by_trajectory: dict[str, list[float]] = {f"F{i}": [] for i in range(6)}
    for key, a3 in indexed.items():
        if key[-1] != 3:
            continue
        a2 = indexed[key[:-1] + (2,)]
        difference = float(a3["output_snr_db"]) - float(a2["output_snr_db"])
        differences.append(difference)
        by_trajectory[str(a3["trajectory"])].append(difference)
        reductions.append(
            (float(a2["tracker_calls"]) - float(a3["tracker_calls"]))
            / float(a2["tracker_calls"])
        )
    values = np.asarray(differences)
    return {
        "comparison": "A3 vs A2 on 1620 paired main-matrix inputs",
        "paired_count": values.size,
        "snr_difference_mean_db": float(values.mean()),
        "snr_difference_sd_db": float(values.std(ddof=1)),
        "snr_difference_median_db": float(np.median(values)),
        "snr_difference_iqr_db": [
            float(value) for value in np.quantile(values, [0.25, 0.75])
        ],
        "snr_difference_bootstrap_ci95_db": bootstrap_ci(values, 20260728),
        "tracker_calls_reduction_median": float(np.median(reductions)),
        "by_trajectory": {
            key: {
                "count": len(group),
                "mean_db": float(np.mean(group)),
                "bootstrap_ci95_db": bootstrap_ci(
                    np.asarray(group), 20260728 + int(key[1:])
                ),
            }
            for key, group in by_trajectory.items()
        },
    }


def main() -> None:
    if MANIFEST.exists():
        raise RuntimeError("Phase 4 is already complete; refusing overwrite")
    verify = subprocess.run([sys.executable, str(VERIFY)], cwd=ROOT)
    if verify.returncode:
        raise RuntimeError("Phase-3 freeze verification failed")
    OUT.mkdir(parents=True, exist_ok=True)
    BATCH.mkdir(parents=True, exist_ok=True)
    build_dll()
    library = load_runner()
    rows: list[dict[str, object]] = []
    archives: list[Path] = []
    total_batches = 66
    batch_number = 0
    for trajectory in TRAJECTORIES:
        for amplitude in AMPLITUDES:
            for noise in NOISES:
                batch_number += 1
                print(f"[phase4] {batch_number:02d}/{total_batches} main F{trajectory} P{amplitude} Z{noise}", flush=True)
                batch_rows, archive = run_batch(
                    library, "main", trajectory, amplitude, noise, 0
                )
                rows.extend(batch_rows)
                archives.append(archive)
    for near in NEAR_CASES:
        for amplitude in AMPLITUDES:
            batch_number += 1
            print(f"[phase4] {batch_number:02d}/{total_batches} near N{near} P{amplitude}", flush=True)
            batch_rows, archive = run_batch(
                library, "near", 0, amplitude, 1, near
            )
            rows.extend(batch_rows)
            archives.append(archive)
    fields = sorted({key for row in rows for key in row})
    with ROWS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    stats = paired_statistics(rows)
    STATS_JSON.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    failures = [row for row in rows if row["status"] != "PASS"]
    manifest = {
        "schema_version": "1.0.0",
        "status": "PASS" if not failures and len(rows) == 7920 else "FAIL",
        "freeze_manifest_sha256": sha256(FREEZE),
        "runner_source_sha256": sha256(SOURCE),
        "runner_script_sha256": sha256(Path(__file__).resolve()),
        "run_count": len(rows), "expected_run_count": 7920,
        "main_run_count": sum(row["matrix"] == "main" for row in rows),
        "near_run_count": sum(row["matrix"] == "near" for row in rows),
        "ablation_run_count_reused": 360,
        "ablation_sha256": sha256(
            ROOT / "outputs/phase3_tuning/phase3_candidate_runs.csv"
        ),
        "failed_runs": failures,
        "metrics_csv_sha256": sha256(ROWS_CSV),
        "statistics_json_sha256": sha256(STATS_JSON),
        "batch_archives": {
            str(path.relative_to(ROOT)): sha256(path) for path in archives
        },
        "frozen_test_seeds_first_authorized_use": list(SEEDS),
        "parameters_changed_after_test_read": False,
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": manifest["status"], "runs": len(rows),
        "failures": len(failures), "stats": stats,
    }, ensure_ascii=False, indent=2), flush=True)
    if manifest["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"[phase4] ERROR: {error}", file=sys.stderr, flush=True)
        raise
