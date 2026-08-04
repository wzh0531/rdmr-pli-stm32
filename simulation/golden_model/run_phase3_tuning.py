"""Run the frozen Phase-3 validation-only OFAT tuning matrix.

This runner compiles the production C implementation for each candidate,
pairs every A3 result with an A2 result on the identical generated input,
and records all 360 candidate runs.  Frozen evaluation seeds are rejected.

Host TSC/QPC timing is used only to rank candidates in Phase 3.  It is not
reported as STM32 DWT timing and tracker calls never substitute for timing.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
from typing import Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "firmware" / "core"
HOST_SOURCE = ROOT / "firmware" / "host_test" / "phase3_tuning_case.c"
TUNING_SPACE = (
    ROOT
    / "config"
    / "tuning-space__rdmr-pli__phase3__candidate__v0.1.0.json"
)
PROTOCOL = (
    ROOT
    / "config"
    / "experiment_protocol__rdmr-pli__v0.3.0.json"
)
OUTPUT_DIR = ROOT / "outputs" / "phase3_tuning"
BUILD_DIR = OUTPUT_DIR / "build"
RAW_CSV = OUTPUT_DIR / "phase3_candidate_runs.csv"
REFERENCE_CSV = OUTPUT_DIR / "phase3_a2_reference_runs.csv"
SUMMARY_CSV = OUTPUT_DIR / "phase3_candidate_summary.csv"
RESULT_JSON = OUTPUT_DIR / "phase3_tuning_result.json"
ACCESS_AUDIT_JSON = OUTPUT_DIR / "phase3_seed_access_audit.json"
FROZEN_MANIFEST = (
    ROOT
    / "config"
    / "tuned-parameters__rdmr-pli__phase3__frozen__v1.0.0.json"
)

FROZEN_FILES = {
    (
        ROOT
        / "paper_workspace"
        / "scope"
        / "experiment-protocol__rdmr-pli__cssp-journal__candidate__v0.3.0.md"
    ): "01C2BABA2C3044D20A23C9D9CEC4E25DF54EBC3D08F47FC626407B44B97A6933",
}

PARAMETER_FIELDS = (
    "interval_fast_blocks",
    "interval_mid_blocks",
    "interval_slow_blocks",
    "residual_new_weight",
    "threshold_scale",
    "block_size_samples",
)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    family: str
    level: str
    parameters: dict[str, int | float]

    @property
    def config_id(self) -> str:
        payload = json.dumps(
            self.parameters,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def assert_frozen_files() -> dict[str, str]:
    actual: dict[str, str] = {}
    for path, expected in FROZEN_FILES.items():
        value = sha256(path)
        actual[str(path.relative_to(ROOT))] = value
        if value != expected:
            raise RuntimeError(
                f"Frozen file hash mismatch: {path}\n"
                f"expected={expected}\nactual={value}"
            )
    return actual


def validation_seeds(
    space: dict[str, object],
    protocol: dict[str, object],
) -> list[int]:
    scenario = space["validation_scenarios"]
    requested = scenario["seeds"]
    seeds = list(range(int(requested["start"]), int(requested["end"]) + 1))
    partitions = protocol["seed_partitions"]
    protocol_seeds = list(
        range(
            int(partitions["validation_start"]),
            int(partitions["validation_end"]) + 1,
        )
    )
    if seeds != protocol_seeds:
        raise RuntimeError("Tuning space and protocol validation seeds differ")
    forbidden = space["forbidden_evaluation_seeds"]
    forbidden_set = set(
        range(int(forbidden["start"]), int(forbidden["end"]) + 1)
    )
    overlap = sorted(set(seeds) & forbidden_set)
    if overlap:
        raise RuntimeError(f"Validation/frozen seed overlap: {overlap}")
    return seeds


def candidate_id(family: str, level: object) -> str:
    if family == "state_intervals":
        values = [int(value) for value in level]
        return f"intervals-{values[0]}-{values[1]}-{values[2]}"
    if family == "residual_new_weight":
        return f"residual-new-{float(level):.2f}".replace(".", "p")
    if family == "threshold_scale":
        return f"threshold-scale-{float(level):.2f}".replace(".", "p")
    if family == "block_size_samples":
        return f"block-size-{int(level)}"
    raise ValueError(f"Unsupported family: {family}")


def build_candidates(space: dict[str, object]) -> list[Candidate]:
    baseline = dict(space["baseline_parameters"])
    candidates: list[Candidate] = []
    for family_spec in space["families"]:
        family = str(family_spec["name"])
        for level in family_spec["levels"]:
            parameters = dict(baseline)
            if family == "state_intervals":
                (
                    parameters["interval_fast_blocks"],
                    parameters["interval_mid_blocks"],
                    parameters["interval_slow_blocks"],
                ) = [int(value) for value in level]
                level_text = "/".join(str(int(value)) for value in level)
            else:
                parameters[family] = level
                level_text = str(level)
            candidates.append(
                Candidate(
                    candidate_id=candidate_id(family, level),
                    family=family,
                    level=level_text,
                    parameters=parameters,
                )
            )
    if len(candidates) != 12:
        raise RuntimeError(f"Expected 12 candidates, got {len(candidates)}")
    return candidates


def compiler_definitions(parameters: dict[str, int | float]) -> list[str]:
    def float_literal(value: int | float) -> str:
        text = f"{float(value):.9g}"
        if "." not in text and "e" not in text.lower():
            text += ".0"
        return text + "f"

    return [
        f"-DRDMR_INTERVAL_FAST={int(parameters['interval_fast_blocks'])}U",
        f"-DRDMR_INTERVAL_MID={int(parameters['interval_mid_blocks'])}U",
        f"-DRDMR_INTERVAL_SLOW={int(parameters['interval_slow_blocks'])}U",
        (
            "-DRDMR_RESIDUAL_NEW_WEIGHT="
            f"{float_literal(parameters['residual_new_weight'])}"
        ),
        (
            "-DRDMR_THRESHOLD_SCALE="
            f"{float_literal(parameters['threshold_scale'])}"
        ),
        f"-DRDMR_BLOCK_SIZE={int(parameters['block_size_samples'])}U",
    ]


def compile_case(
    compiler: str,
    executable: Path,
    parameters: dict[str, int | float],
) -> None:
    command = [
        compiler,
        "-std=c99",
        "-O2",
        "-Wall",
        "-Wextra",
        *compiler_definitions(parameters),
        str(HOST_SOURCE.relative_to(ROOT)),
        str((CORE / "rdmr_algorithm.c").relative_to(ROOT)),
        str((CORE / "rdmr_pli.c").relative_to(ROOT)),
        str((CORE / "rdmr_signal_protocol.c").relative_to(ROOT)),
        str((CORE / "rdmr_trig.c").relative_to(ROOT)),
        "-I",
        str(CORE.relative_to(ROOT)),
        "-lm",
        "-o",
        str(executable.relative_to(ROOT)),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Host tuning build failed:\n"
            + completed.stdout
            + completed.stderr
        )


def run_case(executable: Path, algorithm_id: int) -> list[dict[str, str]]:
    completed = subprocess.run(
        [str(executable), str(algorithm_id)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Host tuning executable failed ({executable.name}):\n"
            + completed.stdout
            + completed.stderr
        )
    rows = list(csv.DictReader(completed.stdout.splitlines()))
    if len(rows) != 30:
        raise RuntimeError(
            f"{executable.name}: expected 30 rows, got {len(rows)}"
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def bootstrap_mean_ci(
    values: np.ndarray,
    resamples: int,
    seed: int,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    indices = rng.integers(
        0,
        values.size,
        size=(resamples, values.size),
    )
    means = values[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def stable_candidate_seed(base_seed: int, candidate: Candidate) -> int:
    digest = hashlib.sha256(candidate.candidate_id.encode("utf-8")).digest()
    return base_seed ^ int.from_bytes(digest[:4], "little")


def numeric(row: dict[str, object], field: str) -> float:
    return float(row[field])


def summarize_candidate(
    candidate: Candidate,
    rows: list[dict[str, object]],
    selection: dict[str, object],
) -> dict[str, object]:
    differences = np.asarray(
        [numeric(row, "paired_snr_difference_db") for row in rows],
        dtype=np.float64,
    )
    tsc = np.asarray(
        [numeric(row, "host_tsc_ticks_per_sample") for row in rows],
        dtype=np.float64,
    )
    elapsed_ns = np.asarray(
        [numeric(row, "host_ns_per_sample") for row in rows],
        dtype=np.float64,
    )
    tracker_reductions = np.asarray(
        [numeric(row, "tracker_calls_reduction_fraction") for row in rows],
        dtype=np.float64,
    )
    low, high = bootstrap_mean_ci(
        differences,
        int(selection["bootstrap_resamples"]),
        stable_candidate_seed(
            int(selection["bootstrap_rng_seed"]),
            candidate,
        ),
    )
    summary: dict[str, object] = {
        "candidate_id": candidate.candidate_id,
        "complete_config_id": candidate.config_id,
        "family": candidate.family,
        "level": candidate.level,
        **candidate.parameters,
        "run_count": len(rows),
        "mean_paired_snr_difference_db": float(differences.mean()),
        "median_paired_snr_difference_db": float(np.median(differences)),
        "minimum_paired_snr_difference_db": float(differences.min()),
        "paired_snr_bootstrap_ci95_lower_db": low,
        "paired_snr_bootstrap_ci95_upper_db": high,
        "snr_gate_pass": bool(low > -0.5),
        "median_host_tsc_ticks_per_sample": float(np.median(tsc)),
        "median_host_ns_per_sample": float(np.median(elapsed_ns)),
        "median_tracker_calls_reduction_fraction": float(
            np.median(tracker_reductions)
        ),
        "all_finite": all(int(row["finite"]) == 1 for row in rows),
    }
    return summary


def source_hashes() -> dict[str, str]:
    paths = [
        HOST_SOURCE,
        CORE / "rdmr_algorithm.c",
        CORE / "rdmr_algorithm.h",
        CORE / "rdmr_pli.c",
        CORE / "rdmr_pli.h",
        CORE / "rdmr_signal_protocol.c",
        CORE / "rdmr_signal_protocol.h",
        CORE / "rdmr_trig.c",
        CORE / "rdmr_trig.h",
        TUNING_SPACE,
        PROTOCOL,
        Path(__file__).resolve(),
    ]
    return {
        str(path.relative_to(ROOT)): sha256(path)
        for path in paths
    }


def pair_rows(
    candidate: Candidate,
    candidate_rows: list[dict[str, str]],
    references: dict[tuple[str, int], dict[str, str]],
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for row in candidate_rows:
        key = (row["trajectory"], int(row["seed"]))
        reference = references.get(key)
        if reference is None:
            raise RuntimeError(f"Missing A2 reference for {key}")
        a3_calls = int(row["tracker_calls"])
        a2_calls = int(reference["tracker_calls"])
        if a2_calls <= 0:
            raise RuntimeError(f"Invalid A2 tracker count for {key}")
        enriched.append(
            {
                "candidate_id": candidate.candidate_id,
                "complete_config_id": candidate.config_id,
                "family": candidate.family,
                "level": candidate.level,
                **candidate.parameters,
                "algorithm": int(row["algorithm"]),
                "paired_reference_algorithm": int(reference["algorithm"]),
                "trajectory": row["trajectory"],
                "seed": int(row["seed"]),
                "output_snr_db": float(row["output_snr_db"]),
                "a2_output_snr_db": float(reference["output_snr_db"]),
                "paired_snr_difference_db": (
                    float(row["output_snr_db"])
                    - float(reference["output_snr_db"])
                ),
                "frequency_mae_hz": float(row["frequency_mae_hz"]),
                "tracker_calls": a3_calls,
                "a2_tracker_calls": a2_calls,
                "tracker_calls_reduction_fraction": (
                    (a2_calls - a3_calls) / a2_calls
                ),
                "state_fast_samples": int(row["state_fast_samples"]),
                "state_mid_samples": int(row["state_mid_samples"]),
                "state_slow_samples": int(row["state_slow_samples"]),
                "state_transitions": int(row["state_transitions"]),
                "host_ns_per_sample": float(row["host_ns_per_sample"]),
                "host_tsc_ticks_per_sample": float(
                    row["host_tsc_ticks_per_sample"]
                ),
                "finite": int(row["finite"]),
            }
        )
    return enriched


def verify_rows(
    all_rows: list[dict[str, object]],
    candidates: list[Candidate],
    expected_seeds: list[int],
    forbidden: set[int],
) -> dict[str, object]:
    expected = len(candidates) * 3 * len(expected_seeds)
    evaluated_seeds = sorted({int(row["seed"]) for row in all_rows})
    trajectories = sorted({str(row["trajectory"]) for row in all_rows})
    finite_values = [
        numeric(row, field)
        for row in all_rows
        for field in (
            "output_snr_db",
            "paired_snr_difference_db",
            "frequency_mae_hz",
            "host_ns_per_sample",
            "host_tsc_ticks_per_sample",
        )
    ]
    errors: list[str] = []
    if len(all_rows) != expected:
        errors.append(f"expected {expected} candidate rows, got {len(all_rows)}")
    if evaluated_seeds != expected_seeds:
        errors.append(
            f"evaluated seeds {evaluated_seeds} != expected {expected_seeds}"
        )
    if forbidden & set(evaluated_seeds):
        errors.append("frozen evaluation seed was evaluated")
    if trajectories != ["F1", "F3", "F4"]:
        errors.append(f"unexpected trajectories: {trajectories}")
    if not all(math.isfinite(value) for value in finite_values):
        errors.append("non-finite numeric result")
    if not all(int(row["finite"]) == 1 for row in all_rows):
        errors.append("C evaluator reported a non-finite result")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "candidate_row_count": len(all_rows),
        "expected_candidate_row_count": expected,
        "evaluated_seeds": evaluated_seeds,
        "evaluated_trajectories": trajectories,
        "forbidden_seed_overlap": sorted(forbidden & set(evaluated_seeds)),
        "frozen_evaluation_seed_values_generated": False,
    }


def select_candidate(
    summaries: list[dict[str, object]],
) -> tuple[dict[str, object], str]:
    eligible = [
        row
        for row in summaries
        if bool(row["snr_gate_pass"]) and bool(row["all_finite"])
    ]
    if not eligible:
        raise RuntimeError(
            "No candidate satisfied the strict paired SNR bootstrap gate"
        )
    eligible.sort(
        key=lambda row: (
            float(row["median_host_tsc_ticks_per_sample"]),
            str(row["candidate_id"]),
        )
    )
    selected = eligible[0]
    reason = (
        "严格先筛选 paired bootstrap 95% CI 下界 > -0.5 dB 且数值有限"
        "的候选，再最小化验证矩阵上的 median host TSC ticks/sample；"
        "若相同则按 candidate_id 字典序。该主机指标只用于 Phase 3 排序，"
        "不是 STM32 DWT 周期证据。"
    )
    return selected, reason


def main() -> None:
    if FROZEN_MANIFEST.exists():
        raise RuntimeError(
            "Phase 3 is frozen. Refusing to overwrite tuning evidence; "
            "create a new versioned tuning/freeze workflow instead."
        )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which("gcc")
    if compiler is None:
        raise RuntimeError("gcc is required for Phase-3 host tuning")

    frozen_before = assert_frozen_files()
    space = load_json(TUNING_SPACE)
    protocol = load_json(PROTOCOL)
    seeds = validation_seeds(space, protocol)
    candidates = build_candidates(space)
    forbidden_spec = space["forbidden_evaluation_seeds"]
    forbidden = set(
        range(
            int(forbidden_spec["start"]),
            int(forbidden_spec["end"]) + 1,
        )
    )
    print(
        f"[phase3] candidates={len(candidates)}, "
        f"validation_seeds={seeds[0]}-{seeds[-1]}",
        flush=True,
    )

    baseline_parameters = dict(space["baseline_parameters"])
    reference_executable = BUILD_DIR / "a2_reference.exe"
    print("[phase3] building/running paired A2 reference", flush=True)
    compile_case(compiler, reference_executable, baseline_parameters)
    reference_rows = run_case(reference_executable, 2)
    references = {
        (row["trajectory"], int(row["seed"])): row
        for row in reference_rows
    }
    write_csv(REFERENCE_CSV, reference_rows)

    execution_order = list(candidates)
    random.Random(20260728).shuffle(execution_order)
    all_rows: list[dict[str, object]] = []
    rows_by_candidate: dict[str, list[dict[str, object]]] = {}
    for index, candidate in enumerate(execution_order, start=1):
        executable = BUILD_DIR / f"{candidate.candidate_id}.exe"
        print(
            f"[phase3] {index:02d}/{len(candidates)} "
            f"{candidate.candidate_id}",
            flush=True,
        )
        compile_case(compiler, executable, candidate.parameters)
        rows = pair_rows(
            candidate,
            run_case(executable, 3),
            references,
        )
        all_rows.extend(rows)
        rows_by_candidate[candidate.candidate_id] = rows

    all_rows.sort(
        key=lambda row: (
            str(row["candidate_id"]),
            str(row["trajectory"]),
            int(row["seed"]),
        )
    )
    write_csv(RAW_CSV, all_rows)

    selection_spec = space["selection_rule"]
    summaries = [
        summarize_candidate(
            candidate,
            rows_by_candidate[candidate.candidate_id],
            selection_spec,
        )
        for candidate in candidates
    ]
    selected, selection_reason = select_candidate(summaries)
    for summary in summaries:
        summary["selected"] = (
            summary["candidate_id"] == selected["candidate_id"]
        )
    write_csv(SUMMARY_CSV, summaries)

    access_audit = verify_rows(
        all_rows,
        candidates,
        seeds,
        forbidden,
    )
    access_audit.update(
        {
            "development_seed_values_generated": False,
            "selection_used_only_validation_rows": True,
            "execution_order": [
                candidate.candidate_id
                for candidate in execution_order
            ],
        }
    )
    ACCESS_AUDIT_JSON.write_text(
        json.dumps(access_audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if access_audit["status"] != "PASS":
        raise RuntimeError(
            "Phase-3 access/completeness audit failed: "
            + "; ".join(access_audit["errors"])
        )

    frozen_after = assert_frozen_files()
    if frozen_after != frozen_before:
        raise RuntimeError("Frozen file hashes changed during Phase-3 tuning")
    result = {
        "schema_version": "0.1.0",
        "status": "PASS",
        "phase": "Phase 3 host tuning candidate selection",
        "protocol_id": space["protocol_id"],
        "matrix": {
            "candidate_runs": len(all_rows),
            "paired_reference_runs": len(reference_rows),
            "candidate_count": len(candidates),
            "trajectories": ["F1", "F3", "F4"],
            "validation_seeds": seeds,
        },
        "selection_rule": selection_spec,
        "selected_candidate": selected,
        "selection_reason": selection_reason,
        "evidence_boundary": {
            "host_timing": (
                "Measured QPC ns/sample and x86 TSC ticks/sample rank "
                "Phase-3 candidates on this host only."
            ),
            "not_established": [
                "STM32 DWT cycle reduction",
                "physical MCU timing",
                "power or energy reduction",
                "frozen-test generalization"
            ],
            "tracker_calls_not_used_as_time": True
        },
        "seed_access_audit": access_audit,
        "frozen_file_hashes_before": frozen_before,
        "frozen_file_hashes_after": frozen_after,
        "source_hashes_at_selection": source_hashes(),
        "artifacts": {
            "candidate_runs_csv": str(RAW_CSV.relative_to(ROOT)),
            "a2_reference_runs_csv": str(REFERENCE_CSV.relative_to(ROOT)),
            "candidate_summary_csv": str(SUMMARY_CSV.relative_to(ROOT)),
            "seed_access_audit_json": str(ACCESS_AUDIT_JSON.relative_to(ROOT))
        }
    }
    RESULT_JSON.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "[phase3] selected="
        f"{selected['candidate_id']}, "
        "ci_lower="
        f"{float(selected['paired_snr_bootstrap_ci95_lower_db']):.6f} dB, "
        "host_tsc="
        f"{float(selected['median_host_tsc_ticks_per_sample']):.3f}",
        flush=True,
    )
    print(f"[phase3] result={RESULT_JSON}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"[phase3] ERROR: {error}", file=sys.stderr, flush=True)
        raise
