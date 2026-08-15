"""Run the frozen Phase-8 multi-record MIT-BIH controlled-PLI experiment."""

from __future__ import annotations

import csv
import ctypes
import hashlib
import json
import math
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = (
    ROOT
    / "sources"
    / "physionet_mitdb_1.0.0"
    / "mit-bih-arrhythmia-database-1.0.0"
)
OUT = ROOT / "outputs" / "phase8_realtime_strengthening" / "mitdb_multirecord"
SELECTION_PATH = OUT / "selection_manifest.json"
LIBRARY_PATH = (
    ROOT
    / "outputs"
    / "phase8_realtime_strengthening"
    / "host_bridge_full"
    / "tracker_hierarchical.dll"
)
N = 8000
FS = 1000.0
ALGORITHMS = {2: "A2", 3: "A3", 7: "B4"}
COMPARISONS = ((3, 2, "A3_minus_A2"), (3, 7, "A3_minus_B4"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_library():
    library = ctypes.CDLL(str(LIBRARY_PATH))
    f32 = np.ctypeslib.ndpointer(np.float32, flags="C_CONTIGUOUS")
    u32 = np.ctypeslib.ndpointer(np.uint32, flags="C_CONTIGUOUS")
    u8 = np.ctypeslib.ndpointer(np.uint8, flags="C_CONTIGUOUS")
    library.optimization_run_external.argtypes = [
        ctypes.c_int, ctypes.c_uint32, f32, f32, f32, f32,
        u32, u32, u32, u8,
    ]
    library.optimization_run_external.restype = ctypes.c_int
    library.optimization_tracker_search_mode.restype = ctypes.c_uint32
    library.optimization_tracker_max_grid_evaluations.restype = ctypes.c_uint32
    if int(library.optimization_tracker_search_mode()) != 1:
        raise RuntimeError("multi-record experiment requires hierarchical search mode 1")
    if int(library.optimization_tracker_max_grid_evaluations()) != 32:
        raise RuntimeError("hierarchical library does not report a 32-point maximum")
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
        algorithm, input_values.size, input_values, output, estimated,
        residual, calls, searches, evaluations, state,
    )
    if code != 1:
        raise RuntimeError(f"runner failed for algorithm {algorithm}: {code}")
    return output, estimated, calls, searches, evaluations


def decode_wfdb_212(record: dict[str, object]) -> np.ndarray:
    raw = np.fromfile(SOURCE_ROOT / f"{record['record']}.dat", dtype=np.uint8)
    triples = raw[: raw.size - raw.size % 3].reshape(-1, 3).astype(np.int16)
    channel_0 = triples[:, 0] | ((triples[:, 1] & 0x0F) << 8)
    channel_1 = triples[:, 2] | ((triples[:, 1] & 0xF0) << 4)
    values = channel_0 if int(record["selected_channel_zero_based"]) == 0 else channel_1
    values = np.where(values >= 2048, values - 4096, values)
    return (
        values.astype(np.float64) - float(record["adc_zero"])
    ) / float(record["gain_adc_units_per_mv"])


def trajectory(index: int, rng: np.random.Generator) -> np.ndarray:
    sample = np.arange(N)
    if index == 0:
        return np.full(N, 50.0)
    if index == 1:
        return np.where(sample < 4000, 49.0, 51.0)
    if index == 2:
        return np.where(sample < 4000, 47.0, 53.0)
    if index == 3:
        return np.where(
            sample < 1000,
            49.0,
            np.where(sample > 6999, 51.0, 49.0 + 2.0 * (sample - 1000) / 5999.0),
        )
    if index == 4:
        return 50.0 + np.sin(2.0 * np.pi * sample / 4000.0)
    values = np.empty(N)
    current = 50.0
    for index_sample in range(N):
        if index_sample and index_sample % 50 == 0:
            current += rng.choice([-0.05, 0.0, 0.05], p=[0.25, 0.5, 0.25])
            if current < 48.5:
                current = 48.5 + (48.5 - current)
            if current > 51.5:
                current = 51.5 - (current - 51.5)
        values[index_sample] = current
    return values


def bootstrap_ci(values: np.ndarray, seed: int, resamples: int = 20000) -> list[float]:
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, values.size, size=(resamples, values.size))
    means = values[indices].mean(axis=1)
    return [float(value) for value in np.quantile(means, (0.025, 0.975))]


def main() -> None:
    selection = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    if selection.get("status") != "FROZEN_BEFORE_ANALYSIS":
        raise RuntimeError("selection manifest is not frozen")
    if selection.get("record_count") != 48 or selection.get("subject_cluster_count") != 47:
        raise RuntimeError("selection manifest record/subject counts changed")
    selection_hash = sha256(SELECTION_PATH)
    library = load_library()
    target_rms = math.sqrt((0.18 ** 2 + 0.10 ** 2) / 2.0)
    rows: list[dict[str, object]] = []

    for record in selection["records"]:
        signal = decode_wfdb_212(record)
        record_number = int(record["record"])
        source_rate = int(record["sample_rate_hz"])
        for segment in record["segments"]:
            segment_index = int(segment["segment_index"])
            start_seconds = int(segment["start_seconds"])
            start = start_seconds * source_rate
            raw_segment = signal[start:start + 8 * source_rate]
            raw_segment = raw_segment - raw_segment.mean()
            source_time = np.arange(raw_segment.size) / float(source_rate)
            clean = np.interp(np.arange(N) / FS, source_time, raw_segment)
            rms = math.sqrt(float(np.mean(clean * clean)))
            if not math.isfinite(rms) or rms <= 0.0:
                raise RuntimeError(f"invalid RMS for record {record_number}, segment {segment_index}")
            clean *= target_rms / rms
            centered_clean = clean - clean.mean()
            desired_energy = float(np.dot(clean, clean))

            for trajectory_index in range(6):
                for amplitude in (0.2, 0.5):
                    for noise_db in (None, 20):
                        seed_base = (
                            202608130000
                            + record_number * 100000
                            + segment_index * 10000
                            + trajectory_index * 1000
                            + int(amplitude * 10) * 10
                            + (0 if noise_db is None else 1)
                        )
                        frequency = trajectory(
                            trajectory_index,
                            np.random.default_rng(seed_base + 11),
                        )
                        phase_0 = np.random.default_rng(seed_base + 23).uniform(0, 2 * np.pi)
                        phase = phase_0 + 2 * np.pi * np.cumsum(
                            np.r_[0.0, frequency[:-1]]
                        ) / FS
                        interference = amplitude * np.sin(phase)
                        noise = np.zeros(N)
                        if noise_db is not None:
                            sigma = math.sqrt(
                                desired_energy / N / (10 ** (noise_db / 10))
                            )
                            noise = sigma * np.random.default_rng(seed_base + 37).normal(size=N)
                        input_values = (clean + interference + noise).astype(np.float32)

                        for algorithm, name in ALGORITHMS.items():
                            output, estimated, calls, searches, evaluations = run_external(
                                library, algorithm, input_values
                            )
                            output64 = output.astype(np.float64)
                            error = output64 - clean
                            centered_output = output64 - output64.mean()
                            denominator = math.sqrt(
                                float(np.dot(centered_clean, centered_clean))
                                * float(np.dot(centered_output, centered_output))
                            )
                            rows.append({
                                "record": str(record["record"]),
                                "subject_cluster": record["subject_cluster"],
                                "selected_lead": record["selected_lead"],
                                "segment": segment_index,
                                "start_seconds": start_seconds,
                                "trajectory": f"F{trajectory_index}",
                                "pli_amplitude": amplitude,
                                "noise": "none" if noise_db is None else "20dB",
                                "algorithm": algorithm,
                                "algorithm_name": name,
                                "output_snr_db": 10.0 * math.log10(
                                    desired_energy / float(np.dot(error, error))
                                ),
                                "prd_percent": 100.0 * math.sqrt(
                                    float(np.dot(error, error))
                                    / float(np.dot(centered_clean, centered_clean))
                                ),
                                "correlation": (
                                    float(np.dot(centered_clean, centered_output)) / denominator
                                ),
                                "frequency_mae_hz": float(np.mean(np.abs(
                                    estimated.astype(np.float64) - frequency
                                ))),
                                "tracker_calls": int(calls[-1]),
                                "tracker_searches": int(searches[-1]),
                                "tracker_grid_evaluations": int(evaluations[-1]),
                            })

    metrics_path = OUT / "mitdb_multirecord_metrics.csv"
    with metrics_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    indexed: dict[tuple[object, ...], dict[int, dict[str, object]]] = {}
    for row in rows:
        key = (
            row["record"], row["subject_cluster"], row["segment"],
            row["trajectory"], row["pli_amplitude"], row["noise"],
        )
        indexed.setdefault(key, {})[int(row["algorithm"])] = row

    paired_rows = []
    for key, algorithms in indexed.items():
        for left, right, comparison in COMPARISONS:
            paired_rows.append({
                "record": key[0],
                "subject_cluster": key[1],
                "segment": key[2],
                "trajectory": key[3],
                "pli_amplitude": key[4],
                "noise": key[5],
                "comparison": comparison,
                "output_snr_difference_db": (
                    float(algorithms[left]["output_snr_db"])
                    - float(algorithms[right]["output_snr_db"])
                ),
                "frequency_mae_difference_hz": (
                    float(algorithms[left]["frequency_mae_hz"])
                    - float(algorithms[right]["frequency_mae_hz"])
                ),
                "tracker_call_difference": (
                    int(algorithms[left]["tracker_calls"])
                    - int(algorithms[right]["tracker_calls"])
                ),
                "grid_evaluation_difference": (
                    int(algorithms[left]["tracker_grid_evaluations"])
                    - int(algorithms[right]["tracker_grid_evaluations"])
                ),
            })
    paired_path = OUT / "mitdb_multirecord_paired_differences.csv"
    with paired_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(paired_rows[0]))
        writer.writeheader()
        writer.writerows(paired_rows)

    subject_rows = []
    for comparison in (item[2] for item in COMPARISONS):
        subset = [row for row in paired_rows if row["comparison"] == comparison]
        subjects = sorted({str(row["subject_cluster"]) for row in subset})
        for subject in subjects:
            group = [row for row in subset if row["subject_cluster"] == subject]
            subject_rows.append({
                "subject_cluster": subject,
                "comparison": comparison,
                "record_count": len({row["record"] for row in group}),
                "paired_condition_count": len(group),
                "mean_output_snr_difference_db": float(np.mean([
                    row["output_snr_difference_db"] for row in group
                ])),
                "mean_frequency_mae_difference_hz": float(np.mean([
                    row["frequency_mae_difference_hz"] for row in group
                ])),
                "mean_tracker_call_difference": float(np.mean([
                    row["tracker_call_difference"] for row in group
                ])),
                "mean_grid_evaluation_difference": float(np.mean([
                    row["grid_evaluation_difference"] for row in group
                ])),
            })
    subject_path = OUT / "mitdb_multirecord_subject_cluster_summary.csv"
    with subject_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(subject_rows[0]))
        writer.writeheader()
        writer.writerows(subject_rows)

    summaries = {}
    for comparison_index, comparison in enumerate(item[2] for item in COMPARISONS):
        group = [row for row in subject_rows if row["comparison"] == comparison]
        snr = np.asarray([row["mean_output_snr_difference_db"] for row in group])
        mae = np.asarray([row["mean_frequency_mae_difference_hz"] for row in group])
        calls = np.asarray([row["mean_tracker_call_difference"] for row in group])
        evaluations = np.asarray([row["mean_grid_evaluation_difference"] for row in group])
        summaries[comparison] = {
            "subject_clusters": int(snr.size),
            "mean_output_snr_difference_db": float(snr.mean()),
            "subject_cluster_bootstrap_ci95_db": bootstrap_ci(
                snr, 2026081500 + comparison_index
            ),
            "minimum_subject_mean_output_snr_difference_db": float(snr.min()),
            "mean_frequency_mae_difference_hz": float(mae.mean()),
            "mean_tracker_call_difference": float(calls.mean()),
            "mean_grid_evaluation_difference": float(evaluations.mean()),
        }

    algorithm_summary = []
    for algorithm, name in ALGORITHMS.items():
        group = [row for row in rows if row["algorithm"] == algorithm]
        algorithm_summary.append({
            "algorithm": algorithm,
            "name": name,
            "runs": len(group),
            "mean_output_snr_db": float(np.mean([row["output_snr_db"] for row in group])),
            "mean_frequency_mae_hz": float(np.mean([row["frequency_mae_hz"] for row in group])),
            "mean_tracker_calls": float(np.mean([row["tracker_calls"] for row in group])),
            "mean_grid_evaluations": float(np.mean([
                row["tracker_grid_evaluations"] for row in group
            ])),
        })

    summary = {
        "status": "PASS",
        "protocol": "rdmr-pli-realtime-strengthening-v0.5.0",
        "selection_manifest_sha256": selection_hash,
        "record_count": 48,
        "subject_cluster_count": 47,
        "segments_per_record": 3,
        "injection_conditions_per_segment": 24,
        "paired_inputs": len(indexed),
        "algorithm_runs": len(rows),
        "algorithm_summary": algorithm_summary,
        "subject_cluster_comparisons": summaries,
        "interpretation_boundary": (
            "controlled PLI injection on public ECG morphology; not clinical, "
            "acquisition-chain, or independent-condition validation"
        ),
    }
    summary_path = OUT / "mitdb_multirecord_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "1.0.0",
        "protocol": "rdmr-pli-realtime-strengthening-v0.5.0",
        "status": "PASS",
        "files": {
            str(path.relative_to(ROOT)): sha256(path)
            for path in (
                SELECTION_PATH, LIBRARY_PATH, metrics_path, paired_path,
                subject_path, summary_path,
            )
        },
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
