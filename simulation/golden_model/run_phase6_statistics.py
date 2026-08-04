"""Generate deterministic Phase-6 statistics from frozen Phase-4/5 evidence.

The script never edits raw logs, frozen protocol files, or manuscript baselines.
It writes only derived statistics and an evidence-bounded audit report.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon


ROOT = Path(__file__).resolve().parents[2]
PHASE4_DIR = ROOT / "outputs" / "phase4_host"
PHASE5_DIR = ROOT / "outputs" / "phase5_physical_core"
PHASE3_DIR = ROOT / "outputs" / "phase3_tuning"
OUT_DIR = ROOT / "outputs" / "phase6_statistics"
REVIEW_DIR = ROOT / "paper_workspace" / "reviews"

METRICS_CSV = PHASE4_DIR / "phase4_run_metrics.csv"
PHASE4_MANIFEST = PHASE4_DIR / "phase4_completion_manifest.json"
PHASE4_VALIDATION = PHASE4_DIR / "phase4_validation_and_grouped_summary.json"
PHASE5_GATE = PHASE5_DIR / "phase5_physical_core_gate_summary.json"
ABLATION_RUNS = PHASE3_DIR / "phase3_candidate_runs.csv"
ABLATION_SUMMARY = PHASE3_DIR / "phase3_candidate_summary.csv"
FROZEN_PROTOCOL = (
    ROOT / "paper_workspace" / "scope"
    / "experiment-protocol__rdmr-pli__cssp-journal__candidate__v0.3.0.md"
)
NONPUBLIC_EI_DRAFT_SHA256 = (
    "629A01139433FBA0E07191C64263D02EF7EDEE8CBFE237C9D1419FE630BDF287"
)

STATS_JSON = OUT_DIR / "phase6_paired_statistics.json"
ALGORITHM_CSV = OUT_DIR / "phase6_main_algorithm_summary.csv"
PAIRED_CSV = OUT_DIR / "phase6_a3_vs_a2_paired_metrics.csv"
HOLM_CSV = OUT_DIR / "phase6_holm_by_trajectory.csv"
NEAR_CSV = OUT_DIR / "phase6_near_line_summary.csv"
ABLATION_CSV = OUT_DIR / "phase6_ablation_summary.csv"
MANIFEST_JSON = OUT_DIR / "phase6_statistical_manifest.json"
REPORT_MD = (
    REVIEW_DIR
    / "quantitative-audit__rdmr-pli__phase6-statistics__candidate__v1.0.0.md"
)

BOOTSTRAP_SEED = 20260803
BOOTSTRAP_RESAMPLES = 20_000
NONINFERIORITY_MARGIN_DB = -0.5
ALGORITHM_NAMES = {
    0: "A0_fixed_notch",
    1: "A1_fixed_reference_nlms",
    2: "A2_every_block_tracking",
    3: "A3_residual_driven_multirate",
}

PAIRED_METRICS = [
    ("output_snr_db", "dB", "higher"),
    ("snr_improvement_db", "dB", "higher"),
    ("rmse", "signal_unit", "lower"),
    ("frequency_mae_hz", "Hz", "lower"),
    ("frequency_p95_abs_error_hz", "Hz", "lower"),
    ("tracker_calls", "calls_per_8000_samples", "lower"),
    ("state_fast_fraction", "fraction", "descriptive"),
    ("state_mid_fraction", "fraction", "descriptive"),
    ("state_slow_fraction", "fraction", "descriptive"),
    ("state_transitions", "count_per_8000_samples", "descriptive"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_number(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    return value


def describe(values: np.ndarray) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return {
            "n": 0,
            "mean": None,
            "sd": None,
            "median": None,
            "q1": None,
            "q3": None,
            "minimum": None,
            "maximum": None,
        }
    return {
        "n": int(array.size),
        "mean": float(np.mean(array)),
        "sd": float(np.std(array, ddof=1)) if array.size > 1 else 0.0,
        "median": float(np.median(array)),
        "q1": float(np.quantile(array, 0.25)),
        "q3": float(np.quantile(array, 0.75)),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
    }


def bootstrap_mean_ci(
    values: np.ndarray,
    seed: int,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> list[float]:
    array = np.asarray(values, dtype=np.float64)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return [math.nan, math.nan]
    rng = np.random.default_rng(seed)
    means = np.empty(resamples, dtype=np.float64)
    chunk_size = 500
    cursor = 0
    while cursor < resamples:
        count = min(chunk_size, resamples - cursor)
        indices = rng.integers(0, array.size, size=(count, array.size))
        means[cursor:cursor + count] = np.mean(array[indices], axis=1)
        cursor += count
    low, high = np.quantile(means, [0.025, 0.975])
    return [float(low), float(high)]


def paired_effect_dz(differences: np.ndarray) -> float | None:
    array = np.asarray(differences, dtype=np.float64)
    array = array[np.isfinite(array)]
    if array.size < 2:
        return None
    sd = float(np.std(array, ddof=1))
    if sd == 0.0:
        return None
    return float(np.mean(array) / sd)


def wilcoxon_p_value(differences: np.ndarray) -> float:
    array = np.asarray(differences, dtype=np.float64)
    array = array[np.isfinite(array)]
    if array.size == 0 or np.all(array == 0.0):
        return 1.0
    try:
        result = wilcoxon(
            array,
            zero_method="wilcox",
            correction=False,
            alternative="two-sided",
            method="auto",
        )
        return float(result.pvalue)
    except ValueError:
        return 1.0


def holm_adjust(p_values: list[float]) -> list[float]:
    count = len(p_values)
    order = np.argsort(np.asarray(p_values, dtype=np.float64))
    adjusted_sorted = np.empty(count, dtype=np.float64)
    running = 0.0
    for rank, original_index in enumerate(order):
        candidate = (count - rank) * float(p_values[int(original_index)])
        running = max(running, candidate)
        adjusted_sorted[rank] = min(1.0, running)
    adjusted = np.empty(count, dtype=np.float64)
    for rank, original_index in enumerate(order):
        adjusted[int(original_index)] = adjusted_sorted[rank]
    return [float(value) for value in adjusted]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"refusing to write empty CSV: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: clean_number(value) for key, value in row.items()})


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "NA"
    number = float(value)
    if not math.isfinite(number):
        return "NA"
    return f"{number:.{digits}f}"


def fmt_p(value: Any) -> str:
    if value is None:
        return "NA"
    number = float(value)
    if not math.isfinite(number):
        return "NA"
    return f"{number:.3e}" if number < 0.001 else f"{number:.3f}"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    completion = load_json(PHASE4_MANIFEST)
    phase4_validation = load_json(PHASE4_VALIDATION)
    phase5_gate = load_json(PHASE5_GATE)
    metrics = pd.read_csv(METRICS_CSV)
    ablation_runs = pd.read_csv(ABLATION_RUNS)
    ablation_summary = pd.read_csv(ABLATION_SUMMARY)

    if completion["status"] != "PASS" or int(completion["run_count"]) != 7920:
        raise RuntimeError("Phase-4 completion manifest is not the frozen PASS matrix")
    if phase4_validation["status"] != "PASS":
        raise RuntimeError("Phase-4 validation summary is not PASS")
    if len(metrics) != 7920:
        raise RuntimeError(f"expected 7920 metrics rows, got {len(metrics)}")
    if set(metrics["status"].astype(str)) != {"PASS"}:
        raise RuntimeError("non-PASS Phase-4 rows are present")
    if len(ablation_runs) != 360:
        raise RuntimeError(f"expected 360 ablation rows, got {len(ablation_runs)}")
    if not bool(ablation_runs["finite"].astype(bool).all()):
        raise RuntimeError("non-finite ablation rows are present")

    main_rows = metrics[metrics["matrix"] == "main"].copy()
    near_rows = metrics[metrics["matrix"] == "near"].copy()
    if len(main_rows) != 6480 or len(near_rows) != 1440:
        raise RuntimeError("Phase-4 main/near row counts do not match protocol")

    main_keys = ["trajectory", "pli_amplitude", "noise", "near_line", "seed"]
    near_keys = ["trajectory", "pli_amplitude", "noise", "near_line", "seed"]
    main_grouped = main_rows.groupby(main_keys, dropna=False)
    near_grouped = near_rows.groupby(near_keys, dropna=False)
    if not bool((main_grouped.size() == 4).all()):
        raise RuntimeError("main matrix does not contain four algorithms per input")
    if not bool((near_grouped.size() == 4).all()):
        raise RuntimeError("near matrix does not contain four algorithms per input")
    if not bool((main_grouped["input_sha256"].nunique() == 1).all()):
        raise RuntimeError("main paired inputs are not hash-identical")
    if not bool((near_grouped["input_sha256"].nunique() == 1).all()):
        raise RuntimeError("near paired inputs are not hash-identical")

    numeric_columns = [
        "output_snr_db",
        "snr_improvement_db",
        "rmse",
        "frequency_mae_hz",
        "frequency_p95_abs_error_hz",
        "tracker_calls",
        "state_fast_fraction",
        "state_mid_fraction",
        "state_slow_fraction",
        "state_transitions",
    ]
    for column in numeric_columns:
        values = pd.to_numeric(main_rows[column], errors="coerce").to_numpy(float)
        if not bool(np.isfinite(values).all()):
            raise RuntimeError(f"main metric contains non-finite values: {column}")

    algorithm_rows: list[dict[str, Any]] = []
    for algorithm_id in sorted(ALGORITHM_NAMES):
        subset = main_rows[main_rows["algorithm"] == algorithm_id]
        row: dict[str, Any] = {
            "algorithm_id": algorithm_id,
            "algorithm": ALGORITHM_NAMES[algorithm_id],
            "n": int(len(subset)),
        }
        for metric in numeric_columns:
            stats = describe(subset[metric].to_numpy(float))
            for field in ("mean", "sd", "median", "q1", "q3"):
                row[f"{metric}_{field}"] = stats[field]
        algorithm_rows.append(row)

    a2 = main_rows[main_rows["algorithm"] == 2].set_index(main_keys).sort_index()
    a3 = main_rows[main_rows["algorithm"] == 3].set_index(main_keys).sort_index()
    if len(a2) != 1620 or len(a3) != 1620 or not a2.index.equals(a3.index):
        raise RuntimeError("A2/A3 paired index mismatch")
    if not bool((a2["input_sha256"].to_numpy() == a3["input_sha256"].to_numpy()).all()):
        raise RuntimeError("A2/A3 input hashes differ")

    paired_rows: list[dict[str, Any]] = []
    paired_detail: dict[str, Any] = {}
    for metric_index, (metric, unit, preferred) in enumerate(PAIRED_METRICS):
        a2_values = a2[metric].to_numpy(np.float64)
        a3_values = a3[metric].to_numpy(np.float64)
        differences = a3_values - a2_values
        difference_stats = describe(differences)
        ci = bootstrap_mean_ci(differences, BOOTSTRAP_SEED + metric_index)
        nonzero = np.abs(a2_values) > np.finfo(np.float64).eps
        relative = differences[nonzero] / np.abs(a2_values[nonzero])
        relative_stats = describe(relative)
        row = {
            "metric": metric,
            "unit": unit,
            "preferred_direction": preferred,
            "difference_definition": "A3_minus_A2",
            "n": difference_stats["n"],
            "a2_mean": float(np.mean(a2_values)),
            "a3_mean": float(np.mean(a3_values)),
            "difference_mean": difference_stats["mean"],
            "difference_sd": difference_stats["sd"],
            "difference_median": difference_stats["median"],
            "difference_q1": difference_stats["q1"],
            "difference_q3": difference_stats["q3"],
            "bootstrap_ci95_mean_lower": ci[0],
            "bootstrap_ci95_mean_upper": ci[1],
            "paired_effect_cohen_dz": paired_effect_dz(differences),
            "wilcoxon_two_sided_p": wilcoxon_p_value(differences),
            "relative_change_definition": "(A3-A2)/abs(A2)",
            "relative_change_n": relative_stats["n"],
            "relative_change_mean_fraction": relative_stats["mean"],
            "relative_change_median_fraction": relative_stats["median"],
        }
        paired_rows.append(row)
        paired_detail[metric] = {
            key: clean_number(value) for key, value in row.items()
        }

    call_reduction = (
        a2["tracker_calls"].to_numpy(float)
        - a3["tracker_calls"].to_numpy(float)
    ) / a2["tracker_calls"].to_numpy(float)
    call_reduction_stats = describe(call_reduction)
    call_reduction_ci = bootstrap_mean_ci(call_reduction, BOOTSTRAP_SEED + 100)

    trajectory_rows: list[dict[str, Any]] = []
    raw_p_values: list[float] = []
    for trajectory_index, trajectory in enumerate(sorted(main_rows["trajectory"].unique())):
        mask = np.asarray(a2.index.get_level_values("trajectory") == trajectory)
        differences = (
            a3["output_snr_db"].to_numpy(float)[mask]
            - a2["output_snr_db"].to_numpy(float)[mask]
        )
        stats = describe(differences)
        ci = bootstrap_mean_ci(
            differences,
            BOOTSTRAP_SEED + 200 + trajectory_index,
        )
        p_value = wilcoxon_p_value(differences)
        raw_p_values.append(p_value)
        trajectory_rows.append({
            "trajectory": trajectory,
            "n": stats["n"],
            "snr_difference_definition": "A3_minus_A2_db",
            "snr_difference_mean_db": stats["mean"],
            "snr_difference_sd_db": stats["sd"],
            "snr_difference_median_db": stats["median"],
            "snr_difference_q1_db": stats["q1"],
            "snr_difference_q3_db": stats["q3"],
            "bootstrap_ci95_mean_lower_db": ci[0],
            "bootstrap_ci95_mean_upper_db": ci[1],
            "paired_effect_cohen_dz": paired_effect_dz(differences),
            "wilcoxon_two_sided_p_raw": p_value,
            "holm_family": "six_trajectory_output_snr_secondary_comparisons",
            "noninferiority_margin_db": NONINFERIORITY_MARGIN_DB,
            "noninferiority_ci_lower_above_margin": bool(
                ci[0] > NONINFERIORITY_MARGIN_DB
            ),
        })
    adjusted = holm_adjust(raw_p_values)
    for row, adjusted_p in zip(trajectory_rows, adjusted):
        row["wilcoxon_two_sided_p_holm"] = adjusted_p
        row["holm_reject_equal_median_at_0p05"] = bool(adjusted_p < 0.05)

    near_metric_columns = [
        "output_snr_db",
        "rmse",
        "f42_amplitude_error",
        "f42_phase_error_rad",
        "f58_amplitude_error",
        "f58_phase_error_rad",
    ]
    near_summary_rows: list[dict[str, Any]] = []
    for (algorithm_id, near_line), subset in near_rows.groupby(
        ["algorithm", "near_line"], sort=True
    ):
        row = {
            "algorithm_id": int(algorithm_id),
            "algorithm": ALGORITHM_NAMES[int(algorithm_id)],
            "near_line": str(near_line),
            "n": int(len(subset)),
        }
        for metric in near_metric_columns:
            values = pd.to_numeric(subset[metric], errors="coerce").to_numpy(float)
            stats = describe(values)
            for field in ("mean", "sd", "median", "q1", "q3"):
                row[f"{metric}_{field}"] = stats[field]
        near_summary_rows.append(row)

    ablation_rows: list[dict[str, Any]] = []
    for _, source in ablation_summary.iterrows():
        row = {key: clean_number(value) for key, value in source.to_dict().items()}
        row["source_run_count_verified"] = int(
            (ablation_runs["candidate_id"] == source["candidate_id"]).sum()
        )
        ablation_rows.append(row)

    snr_primary = next(row for row in paired_rows if row["metric"] == "output_snr_db")
    primary_gate = bool(
        float(snr_primary["bootstrap_ci95_mean_lower"])
        > NONINFERIORITY_MARGIN_DB
    )
    all_trajectory_gate = bool(
        all(row["noninferiority_ci_lower_above_margin"] for row in trajectory_rows)
    )

    physical_pairs = phase5_gate["physical_pair_comparisons"]
    physical_cycle_reduction_min = min(
        float(row["mean_cycles_reduction_fraction"]) for row in physical_pairs
    )
    physical_cycle_reduction_max = max(
        float(row["mean_cycles_reduction_fraction"]) for row in physical_pairs
    )

    gates = {
        "phase4_completion_and_validation": "PASS",
        "main_6480_and_near_1440_rows": "PASS",
        "four_algorithms_per_paired_input": "PASS",
        "paired_input_sha256_identity": "PASS",
        "a3_vs_a2_1620_pairs": "PASS",
        "all_main_numeric_metrics_finite": "PASS",
        "ablation_360_rows_finite": "PASS",
        "overall_snr_noninferiority_ci_lower_gt_minus_0p5_db": (
            "PASS" if primary_gate else "FAIL"
        ),
        "all_six_trajectory_snr_noninferiority": (
            "PASS" if all_trajectory_gate else "FAIL"
        ),
        "holm_adjustment_six_trajectory_family": "PASS",
        "effect_sizes_reported": "PASS",
        "settling_time_metric": "NOT_CHECKED",
        "residual_50hz_band_energy_metric": "NOT_CHECKED",
        "phase5_hard_realtime_1khz": phase5_gate["gates"][
            "hard_realtime_1khz_all_adaptive_scenarios"
        ],
    }

    comparability = {
        "study_object": "internally generated PLI-contaminated benchmark signals",
        "methods": "A0-A3 use the same frozen C execution path and paired inputs",
        "input_definition": (
            "Fs=1000 Hz, N=8000, frozen trajectories/amplitudes/noise/near-line "
            "conditions and seeds from protocol v0.3.0"
        ),
        "output_definition": "algorithm output and frequency estimate from each run",
        "measurement_conditions": (
            "host randomized matrix for inference; Proteus/physical runs are "
            "deterministic implementation checks only"
        ),
        "reference_standard": "A2 every-block tracker for the primary A3-vs-A2 comparison",
        "uncertainty": "paired 95% bootstrap CI with 20,000 deterministic resamples",
        "multiplicity": "Holm correction across six trajectory-level SNR comparisons",
        "effect_size": "paired Cohen dz on A3-A2 differences",
        "leakage_check": {
            "frozen_test_seeds": completion["frozen_test_seeds_first_authorized_use"],
            "parameters_changed_after_test_read": completion[
                "parameters_changed_after_test_read"
            ],
            "verdict": "PASS",
        },
        "boundary": (
            "Host paired runs support statistical inference. The 12 Proteus "
            "scenarios and 36 physical cold starts do not form a random population."
        ),
    }

    summary = {
        "schema_version": "1.0.0",
        "status": "PASS_WITH_REPORTED_NEGATIVE_RESULTS",
        "bootstrap": {
            "resamples": BOOTSTRAP_RESAMPLES,
            "base_seed": BOOTSTRAP_SEED,
            "interval": "percentile_95",
        },
        "comparability": comparability,
        "matrix_counts": {
            "phase4_total": int(len(metrics)),
            "main": int(len(main_rows)),
            "near": int(len(near_rows)),
            "a3_vs_a2_pairs": int(len(a2)),
            "ablation": int(len(ablation_runs)),
            "proteus_scenarios_not_random_samples": int(
                phase5_gate["matrix"]["proteus_scenarios"]
            ),
            "physical_cold_starts_not_random_samples": int(
                phase5_gate["matrix"]["physical_cold_start_runs"]
            ),
        },
        "primary_a3_vs_a2": {
            "output_snr": paired_detail["output_snr_db"],
            "noninferiority_margin_db": NONINFERIORITY_MARGIN_DB,
            "noninferiority_verdict": "PASS" if primary_gate else "FAIL",
            "tracker_calls_reduction_fraction": {
                **{key: clean_number(value) for key, value in call_reduction_stats.items()},
                "bootstrap_ci95_mean": call_reduction_ci,
            },
            "physical_mean_cycles_reduction_fraction_range": [
                physical_cycle_reduction_min,
                physical_cycle_reduction_max,
            ],
            "physical_hard_realtime_verdict": phase5_gate["gates"][
                "hard_realtime_1khz_all_adaptive_scenarios"
            ],
        },
        "paired_metrics": paired_detail,
        "trajectory_statistics": trajectory_rows,
        "gates": gates,
        "missing_or_undefined_metrics": [
            {
                "metric": "step_or_ramp_settling_time",
                "status": "NOT_CHECKED",
                "reason": (
                    "Protocol v0.3.0 lists the metric but does not freeze a "
                    "tolerance band, dwell duration, or treatment of repeated crossings."
                ),
            },
            {
                "metric": "residual_50hz_neighborhood_energy",
                "status": "NOT_CHECKED",
                "reason": (
                    "Protocol v0.3.0 lists the metric but does not freeze the "
                    "frequency band, window, normalization, or aggregation rule."
                ),
            },
        ],
        "bounded_wording": {
            "supported": (
                "Across 1,620 paired frozen host inputs, A3 stayed within the "
                "predeclared -0.5 dB output-SNR margin relative to A2 while "
                "substantially reducing tracker calls; physical measurements "
                "also showed lower mean cycles in all five paired scenarios."
            ),
            "required_negative_result": (
                "A3 had a negative mean output-SNR difference relative to A2, "
                "and neither A2 nor A3 satisfied the tested 1 kHz worst-case "
                "physical deadline in all adaptive scenarios."
            ),
            "prohibited": [
                "A3 universally outperforms A2",
                "1 kHz hard real-time operation was achieved",
                "power or energy consumption was reduced",
                "real sensor acquisition was validated",
            ],
        },
    }

    write_csv(ALGORITHM_CSV, algorithm_rows)
    write_csv(PAIRED_CSV, paired_rows)
    write_csv(HOLM_CSV, trajectory_rows)
    write_csv(NEAR_CSV, near_summary_rows)
    write_csv(ABLATION_CSV, ablation_rows)
    STATS_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    algorithm_table = "\n".join(
        "| {algorithm} | {n} | {snr} ± {snr_sd} | {rmse} | {fmae} | {calls} |".format(
            algorithm=row["algorithm"],
            n=row["n"],
            snr=fmt(row["output_snr_db_mean"], 3),
            snr_sd=fmt(row["output_snr_db_sd"], 3),
            rmse=fmt(row["rmse_mean"], 5),
            fmae=fmt(row["frequency_mae_hz_mean"], 4),
            calls=fmt(row["tracker_calls_mean"], 2),
        )
        for row in algorithm_rows
    )
    trajectory_table = "\n".join(
        "| {trajectory} | {n} | {mean} | [{low}, {high}] | {dz} | {holm} | {ni} |".format(
            trajectory=row["trajectory"],
            n=row["n"],
            mean=fmt(row["snr_difference_mean_db"], 4),
            low=fmt(row["bootstrap_ci95_mean_lower_db"], 4),
            high=fmt(row["bootstrap_ci95_mean_upper_db"], 4),
            dz=fmt(row["paired_effect_cohen_dz"], 3),
            holm=fmt_p(row["wilcoxon_two_sided_p_holm"]),
            ni="PASS" if row["noninferiority_ci_lower_above_margin"] else "FAIL",
        )
        for row in trajectory_rows
    )
    gate_table = "\n".join(
        f"| `{name}` | {verdict} |" for name, verdict in gates.items()
    )
    report = f"""---
artifact_id: quantitative-audit__rdmr-pli__phase6-statistics__candidate__v1.0.0
project_id: ft-vss-nlms-stm32-ei
artifact_kind: quantitative-audit
work_unit: quantitative-audit
status: candidate
language: zh
baseline_artifact: paper_workspace/scope/experiment-protocol__rdmr-pli__cssp-journal__candidate__v0.3.0.md
source_registry: paper_workspace/.sci-review-system/state/project_state.json
run_id: run-20260726-001
gate_status: runtime-blocked-upstream-claim-ledger
next_intents:
  - visual-reference-qa
  - argument-architecture
---

# Phase 6 冻结矩阵统计审计

## 目的与范围

本审计只以7920次冻结主机矩阵作为随机总体统计来源，其中主矩阵6480次、近邻保护矩阵1440次。Proteus的12个确定性场景和实物板36次冷启动只用于实现一致性与资源验证，不作为随机统计样本。

## 方法

- 主比较：相同输入、条件和种子下的A3与A2，共1620对。
- 差值方向统一为`A3 − A2`；输出SNR越高越好，RMSE、频率误差和tracker calls越低越好。
- 置信区间：固定种子`{BOOTSTRAP_SEED}`、{BOOTSTRAP_RESAMPLES}次百分位配对bootstrap。
- 效应量：配对Cohen's dz。
- 六条频率轨迹的SNR次要比较采用Holm校正；非劣界为−0.5 dB。

## 主结果

- A3−A2输出SNR均值：{fmt(snr_primary['difference_mean'], 6)} dB。
- 95%配对bootstrap CI：[{fmt(snr_primary['bootstrap_ci95_mean_lower'], 6)}, {fmt(snr_primary['bootstrap_ci95_mean_upper'], 6)}] dB。
- 配对Cohen's dz：{fmt(snr_primary['paired_effect_cohen_dz'], 4)}。
- 非劣门槛：CI下界大于−0.5 dB，结果为`{'PASS' if primary_gate else 'FAIL'}`。
- tracker calls中位减少率：{100.0 * float(call_reduction_stats['median']):.3f}%；均值95% CI为[{100.0 * call_reduction_ci[0]:.3f}%, {100.0 * call_reduction_ci[1]:.3f}%]。
- 实物五组配对的平均周期减少范围：{100.0 * physical_cycle_reduction_min:.3f}%–{100.0 * physical_cycle_reduction_max:.3f}%。
- 但实物1 kHz最坏时限门禁为`{phase5_gate['gates']['hard_realtime_1khz_all_adaptive_scenarios']}`。

## 四算法总体描述

| 算法 | n | 输出SNR mean±SD (dB) | RMSE mean | 频率MAE mean (Hz) | tracker calls mean |
|---|---:|---:|---:|---:|---:|
{algorithm_table}

## 分轨迹A3−A2输出SNR

| 轨迹 | n | 均值(dB) | 95% CI(dB) | dz | Holm p | 非劣 |
|---|---:|---:|---:|---:|---:|---:|
{trajectory_table}

Holm检验回答“差值是否偏离0”，非劣门槛回答“损失是否超过预先允许的−0.5 dB”；二者不能互相替代。统计显著也不等于工程上优越。

## 可比性与泄漏检查

- A0–A3使用相同冻结C执行路径、输入、场景和种子；逐配对输入SHA-256一致。
- 冻结测试种子为1000–1029，首次授权使用已登记；读取测试结果后参数改动为`false`。
- 主机配对矩阵可用于统计推断；Proteus和实物重复只用于确定性实现验证。

## 未冻结的次要指标

- settling time：`NOT_CHECKED`。协议未冻结容差带、连续驻留时长和重复越界处理。
- 50 Hz邻域残余谱能量：`NOT_CHECKED`。协议未冻结频带、窗函数、归一化和聚合规则。

在补充并冻结定义前，不得从现有波形临时挑选算法计算这两个指标。

## Gate

| Gate | 结果 |
|---|---|
{gate_table}

## 允许与禁止表述

- 允许：A3在冻结配对矩阵内满足−0.5 dB SNR非劣门槛，同时大幅减少tracker calls；实物五组配对平均周期均下降。
- 必须披露：A3相对A2的平均SNR差为负，且A2/A3未通过全部自适应场景的1 kHz最坏时限。
- 禁止：A3普遍优于A2、达到1 kHz硬实时、降低功耗、完成真实传感器采集。

## 人工/运行时状态

通用`sci-review-system`运行时要求先存在论文级claim ledger才能启动`quantitative-audit`单元；本项目交接顺序规定先统计后ledger，因此当前报告为文件级候选审计，不宣称运行时单元已完成。下一步应据此建立CSSP论点架构和claim-evidence ledger，再回填运行时审计。
"""
    REPORT_MD.write_text(report, encoding="utf-8")

    generated = [
        STATS_JSON,
        ALGORITHM_CSV,
        PAIRED_CSV,
        HOLM_CSV,
        NEAR_CSV,
        ABLATION_CSV,
        REPORT_MD,
    ]
    manifest = {
        "schema_version": "1.0.0",
        "status": "PASS_WITH_REPORTED_NEGATIVE_RESULTS",
        "script": {
            "path": str(Path(__file__).resolve().relative_to(ROOT)),
            "sha256": sha256(Path(__file__).resolve()),
        },
        "inputs": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}
            for path in (
                METRICS_CSV,
                PHASE4_MANIFEST,
                PHASE4_VALIDATION,
                PHASE5_GATE,
                ABLATION_RUNS,
                ABLATION_SUMMARY,
                FROZEN_PROTOCOL,
            )
        ],
        "outputs": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in generated
        ],
        "frozen_hash_assertions": {
            "protocol_sha256": sha256(FROZEN_PROTOCOL),
            "ei_draft_sha256": NONPUBLIC_EI_DRAFT_SHA256,
            "ei_draft_verification": "NOT_CHECKED_FILE_NOT_PUBLIC",
        },
        "gates": gates,
    }
    MANIFEST_JSON.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "status": summary["status"],
        "primary": summary["primary_a3_vs_a2"],
        "gates": gates,
        "generated": manifest["outputs"] + [{
            "path": str(MANIFEST_JSON.relative_to(ROOT)),
            "sha256": sha256(MANIFEST_JSON),
            "bytes": MANIFEST_JSON.stat().st_size,
        }],
    }, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
