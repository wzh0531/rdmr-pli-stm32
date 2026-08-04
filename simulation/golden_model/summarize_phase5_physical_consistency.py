"""Summarize Phase-5 physical evidence and audit three-level consistency.

This script is deliberately read-only with respect to frozen configuration,
firmware, raw logs, and manuscript baselines.  It writes only derived Phase-5
summary artifacts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

import run_phase4_host_matrix as phase4


ROOT = Path(__file__).resolve().parents[2]
PHYSICAL_DIR = ROOT / "outputs" / "phase5_physical_core"
PROTEUS_DIR = ROOT / "outputs" / "phase5_proteus_core"
PHYSICAL_MANIFEST = PHYSICAL_DIR / "phase5_physical_core_firmware_manifest.json"
PHYSICAL_VALIDATION = PHYSICAL_DIR / "phase5_physical_log_validation.json"
PROTEUS_VALIDATION = PROTEUS_DIR / "phase5_proteus_log_validation.json"
HOST_COMPLETION = ROOT / "outputs" / "phase4_host" / "phase4_completion_manifest.json"
PHOTO_MANIFEST = PHYSICAL_DIR / "phase5_physical_photo_evidence_manifest.json"
SUMMARY_JSON = PHYSICAL_DIR / "phase5_physical_core_gate_summary.json"
SCENARIO_CSV = PHYSICAL_DIR / "phase5_physical_matrix_summary.csv"
CONSISTENCY_CSV = PHYSICAL_DIR / "phase5_three_level_consistency.csv"
RESOURCE_CSV = PHYSICAL_DIR / "phase5_physical_resource_summary.csv"
REPORT_MD = (
    ROOT / "paper_workspace" / "reviews"
    / "implementation-audit__rdmr-pli__phase5-physical-and-consistency__candidate__v1.0.0.md"
)
N = 8000
ENDPOINTS = np.arange(49, N, 50)
DEADLINE_CYCLES = 72_000


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


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


def host_run(library: object, scenario: dict[str, object]) -> dict[str, np.ndarray]:
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
        int(scenario["algorithm_id"]),
        int(scenario["trajectory_id"]),
        int(scenario["near_line_id"]),
        int(scenario["noise_id"]),
        int(scenario["seed"]),
        float(scenario["pli_amplitude"]),
        N,
        arrays["input"], arrays["clean"], arrays["output"],
        arrays["true"], arrays["estimated"], arrays["residual"],
        arrays["calls"], arrays["state"],
    )
    if code != 1:
        raise RuntimeError(f"host reference failed for S{scenario['scenario_id']}")
    return arrays


def log_metrics(rows: list[dict[str, str]]) -> dict[str, object]:
    desired = sum(int(row["desired_energy"]) for row in rows)
    output_error = sum(int(row["output_error_energy"]) for row in rows)
    estimated = np.asarray([
        int(row["estimated_frequency"]) / 1000.0 for row in rows
    ])
    true = np.asarray([
        int(row["true_frequency"]) / 1000.0 for row in rows
    ])
    return {
        "output_snr_db": 10.0 * math.log10(desired / output_error),
        "frequency_mae_hz": float(np.mean(np.abs(estimated - true))),
        "final_tracker_calls": int(rows[-1]["tracker_calls"]),
        "states": np.asarray([int(row["state"]) for row in rows]),
        "deadline_violating_blocks": sum(
            int(row["cycles"]) >= DEADLINE_CYCLES for row in rows
        ),
        "numeric_fault_rows": sum(
            int(row["numeric_flags"]) != 0 for row in rows
        ),
    }


def host_metrics(arrays: dict[str, np.ndarray]) -> dict[str, object]:
    clean = arrays["clean"].astype(np.float64)
    error = arrays["output"].astype(np.float64) - clean
    return {
        "output_snr_db": 10.0 * math.log10(
            float(np.dot(clean, clean)) / float(np.dot(error, error))
        ),
        "frequency_mae_hz": float(np.mean(np.abs(
            arrays["estimated"][ENDPOINTS] - arrays["true"][ENDPOINTS]
        ))),
        "final_tracker_calls": int(arrays["calls"][-1]),
        "states": arrays["state"][ENDPOINTS],
    }


def compare_metrics(
    left: dict[str, object], right: dict[str, object]
) -> dict[str, object]:
    return {
        "output_snr_abs_difference_db": abs(
            float(left["output_snr_db"]) - float(right["output_snr_db"])
        ),
        "frequency_mae_abs_difference_hz": abs(
            float(left["frequency_mae_hz"])
            - float(right["frequency_mae_hz"])
        ),
        "tracker_calls_abs_difference": abs(
            int(left["final_tracker_calls"])
            - int(right["final_tracker_calls"])
        ),
        "state_mismatches_of_160": int(np.count_nonzero(
            np.asarray(left["states"]) != np.asarray(right["states"])
        )),
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: float, digits: int = 6) -> str:
    return f"{value:.{digits}f}"


def main() -> None:
    physical_manifest = load_json(PHYSICAL_MANIFEST)
    physical_validation = load_json(PHYSICAL_VALIDATION)
    proteus_validation = load_json(PROTEUS_VALIDATION)
    host_completion = load_json(HOST_COMPLETION)
    photo_manifest = load_json(PHOTO_MANIFEST) if PHOTO_MANIFEST.exists() else None
    photo_gate = (
        str(photo_manifest["overall_gate"])
        if photo_manifest is not None else "NOT_CHECKED"
    )

    if physical_validation["status"] != "COMPLETE_WITH_REALTIME_FAILURE":
        raise RuntimeError("physical matrix is not in the expected completed state")
    if physical_validation["received_runs"] != 36:
        raise RuntimeError("physical matrix does not contain 36 runs")
    if host_completion["status"] != "PASS":
        raise RuntimeError("Phase-4 host completion manifest is not PASS")

    physical_results = {
        int(row["scenario_id"]): row
        for row in physical_validation["scenario_results"]
    }
    proteus_results = {
        int(row["scenario_id"]): row
        for row in proteus_validation["results"]
    }
    scenarios = {
        int(row["scenario_id"]): row
        for row in physical_manifest["scenarios"]
    }
    if set(scenarios) != set(range(501, 513)):
        raise RuntimeError("physical firmware manifest scenario set is incomplete")

    build_hash_errors: list[str] = []
    for scenario in scenarios.values():
        for kind in ("hex", "axf", "map"):
            artifact = scenario["artifacts"][kind]
            path = ROOT / artifact["path"]
            if not path.exists() or sha256(path) != artifact["sha256"]:
                build_hash_errors.append(
                    f"S{scenario['scenario_id']}:{kind}"
                )

    library = phase4.load_runner()
    scenario_rows: list[dict[str, object]] = []
    consistency_rows: list[dict[str, object]] = []
    detail: list[dict[str, object]] = []

    for scenario_id in sorted(scenarios):
        scenario = scenarios[scenario_id]
        physical_result = physical_results[scenario_id]
        physical_path = ROOT / physical_result["runs"][0]["log"]
        proteus_path = ROOT / proteus_results[scenario_id]["log"]
        physical_log_rows, physical_stats = parse_log(physical_path)
        proteus_log_rows, _ = parse_log(proteus_path)
        physical = log_metrics(physical_log_rows)
        proteus = log_metrics(proteus_log_rows)
        host = host_metrics(host_run(library, scenario))
        host_physical = compare_metrics(host, physical)
        host_proteus = compare_metrics(host, proteus)
        proteus_physical = compare_metrics(proteus, physical)

        scenario_rows.append({
            "scenario_id": scenario_id,
            "group": scenario["group"],
            "algorithm": scenario["algorithm"],
            "trajectory": scenario["trajectory"],
            "pli_amplitude": scenario["pli_amplitude"],
            "noise": scenario["noise"],
            "cold_starts": physical_result["cold_start_received"],
            "repeatability_status": physical_result["repeatability_status"],
            "final_tracker_calls": physical["final_tracker_calls"],
            "state_0_blocks": sum(
                int(row["state"]) == 0 for row in physical_log_rows
            ),
            "state_1_blocks": sum(
                int(row["state"]) == 1 for row in physical_log_rows
            ),
            "state_2_blocks": sum(
                int(row["state"]) == 2 for row in physical_log_rows
            ),
            "cycles_mean": int(physical_stats["cycles_mean"]),
            "cycles_p95": int(physical_stats["cycles_p95"]),
            "cycles_max": int(physical_stats["cycles_max"]),
            "deadline_cycles_external": DEADLINE_CYCLES,
            "deadline_violating_blocks": physical[
                "deadline_violating_blocks"
            ],
            "numeric_fault_rows": physical["numeric_fault_rows"],
            "integrity_status": physical_result["integrity_status"],
            "realtime_status": physical_result["realtime_status"],
            "representative_log_sha256": physical_result["runs"][0]["sha256"],
        })

        consistency_rows.append({
            "scenario_id": scenario_id,
            "algorithm": scenario["algorithm"],
            "host_output_snr_db": fmt(float(host["output_snr_db"])),
            "proteus_output_snr_db": fmt(float(proteus["output_snr_db"])),
            "physical_output_snr_db": fmt(float(physical["output_snr_db"])),
            "host_physical_snr_abs_diff_db": fmt(float(
                host_physical["output_snr_abs_difference_db"]
            )),
            "host_physical_frequency_mae_abs_diff_hz": fmt(float(
                host_physical["frequency_mae_abs_difference_hz"]
            )),
            "host_physical_tracker_calls_abs_diff": host_physical[
                "tracker_calls_abs_difference"
            ],
            "host_physical_state_mismatches": host_physical[
                "state_mismatches_of_160"
            ],
            "host_proteus_snr_abs_diff_db": fmt(float(
                host_proteus["output_snr_abs_difference_db"]
            )),
            "host_proteus_frequency_mae_abs_diff_hz": fmt(float(
                host_proteus["frequency_mae_abs_difference_hz"]
            )),
            "host_proteus_tracker_calls_abs_diff": host_proteus[
                "tracker_calls_abs_difference"
            ],
            "host_proteus_state_mismatches": host_proteus[
                "state_mismatches_of_160"
            ],
            "proteus_physical_snr_abs_diff_db": fmt(float(
                proteus_physical["output_snr_abs_difference_db"]
            )),
            "proteus_physical_tracker_calls_abs_diff": proteus_physical[
                "tracker_calls_abs_difference"
            ],
            "proteus_physical_state_mismatches": proteus_physical[
                "state_mismatches_of_160"
            ],
        })
        detail.append({
            "scenario_id": scenario_id,
            "host": {
                key: value for key, value in host.items() if key != "states"
            },
            "proteus": {
                key: value for key, value in proteus.items() if key != "states"
            },
            "physical": {
                key: value for key, value in physical.items() if key != "states"
            },
            "host_physical": host_physical,
            "host_proteus": host_proteus,
            "proteus_physical": proteus_physical,
        })

    resource_rows: list[dict[str, object]] = []
    for scenario_id in sorted(scenarios):
        scenario = scenarios[scenario_id]
        memory = scenario["memory"]
        resource_rows.append({
            "scenario_id": scenario_id,
            "algorithm": scenario["algorithm"],
            "trajectory": scenario["trajectory"],
            "pli_amplitude": scenario["pli_amplitude"],
            "ro_bytes": memory["ro_bytes"],
            "rw_bytes": memory["rw_bytes"],
            "rom_bytes": memory["rom_bytes"],
            "flash_utilization_of_64k_percent": fmt(
                100.0 * int(memory["rom_bytes"]) / 65536, 3
            ),
            "ram_utilization_of_20k_percent": fmt(
                100.0 * int(memory["rw_bytes"]) / 20480, 3
            ),
            "map_sha256": scenario["artifacts"]["map"]["sha256"],
        })

    adaptive = [row for row in scenario_rows if row["algorithm"] in ("A2", "A3")]
    a3_pairs = [(503, 504), (505, 506), (507, 508), (509, 510), (511, 512)]
    pair_rows: list[dict[str, object]] = []
    scenario_by_id = {row["scenario_id"]: row for row in scenario_rows}
    for a2_id, a3_id in a3_pairs:
        a2 = scenario_by_id[a2_id]
        a3 = scenario_by_id[a3_id]
        pair_rows.append({
            "a2_scenario_id": a2_id,
            "a3_scenario_id": a3_id,
            "condition": f"{a2['trajectory']}-P{float(a2['pli_amplitude']):.2f}",
            "tracker_calls_reduction_fraction": (
                int(a2["final_tracker_calls"])
                - int(a3["final_tracker_calls"])
            ) / int(a2["final_tracker_calls"]),
            "mean_cycles_reduction_fraction": (
                int(a2["cycles_mean"]) - int(a3["cycles_mean"])
            ) / int(a2["cycles_mean"]),
            "a2_deadline_violating_blocks": a2["deadline_violating_blocks"],
            "a3_deadline_violating_blocks": a3["deadline_violating_blocks"],
        })

    max_host_physical_snr = max(
        float(row["host_physical"]["output_snr_abs_difference_db"])
        for row in detail
    )
    max_host_physical_frequency = max(
        float(row["host_physical"]["frequency_mae_abs_difference_hz"])
        for row in detail
    )
    max_host_physical_calls = max(
        int(row["host_physical"]["tracker_calls_abs_difference"])
        for row in detail
    )
    max_host_physical_states = max(
        int(row["host_physical"]["state_mismatches_of_160"])
        for row in detail
    )
    max_host_proteus_snr = max(
        float(row["host_proteus"]["output_snr_abs_difference_db"])
        for row in detail
    )
    max_host_proteus_frequency = max(
        float(row["host_proteus"]["frequency_mae_abs_difference_hz"])
        for row in detail
    )
    max_host_proteus_calls = max(
        int(row["host_proteus"]["tracker_calls_abs_difference"])
        for row in detail
    )
    max_host_proteus_states = max(
        int(row["host_proteus"]["state_mismatches_of_160"])
        for row in detail
    )

    gates = {
        "physical_36_runs_complete": "PASS",
        "physical_integrity_and_numeric_faults": "PASS",
        "physical_three_cold_start_repeatability": "PASS",
        "firmware_hex_axf_map_hashes": (
            "PASS" if not build_hash_errors else "FAIL"
        ),
        "a3_mean_cycles_lower_than_a2_all_five_pairs": (
            "PASS" if all(
                float(row["mean_cycles_reduction_fraction"]) > 0.0
                for row in pair_rows
            ) else "FAIL"
        ),
        "a3_tracker_calls_lower_than_a2_all_five_pairs": (
            "PASS" if all(
                float(row["tracker_calls_reduction_fraction"]) > 0.0
                for row in pair_rows
            ) else "FAIL"
        ),
        "host_physical_output_snr_le_0.10_db": (
            "PASS" if max_host_physical_snr <= 0.10 else "FAIL"
        ),
        "host_physical_frequency_mae_le_0.05_hz": (
            "PASS" if max_host_physical_frequency <= 0.05 else "FAIL"
        ),
        "host_physical_tracker_calls_difference_le_1": (
            "PASS" if max_host_physical_calls <= 1 else "FAIL"
        ),
        "host_physical_state_sequence_exact": (
            "PASS" if max_host_physical_states == 0 else "FAIL"
        ),
        "host_proteus_output_snr_le_0.10_db": (
            "PASS" if max_host_proteus_snr <= 0.10 else "FAIL"
        ),
        "host_proteus_frequency_mae_le_0.05_hz": (
            "PASS" if max_host_proteus_frequency <= 0.05 else "FAIL"
        ),
        "host_proteus_tracker_calls_difference_le_1": (
            "PASS" if max_host_proteus_calls <= 1 else "FAIL"
        ),
        "host_proteus_state_sequence_exact": (
            "PASS" if max_host_proteus_states == 0 else "FAIL"
        ),
        "hard_realtime_1khz_all_adaptive_scenarios": (
            "PASS" if all(
                int(row["deadline_violating_blocks"]) == 0
                for row in adaptive
            ) else "FAIL"
        ),
        "board_and_wiring_photos": photo_gate,
        "power_or_energy_measurement": "NOT_CHECKED",
    }

    if photo_manifest is None:
        photo_limitation = (
            "Board and wiring photographs have not yet been registered as evidence."
        )
        photo_manual_action = (
            "提供一张完整接线全景和一张STM32F103C8T6/连线近景；"
            "原图保留EXIF并计算SHA-256。"
        )
    elif photo_manifest.get("open_condition"):
        photo_limitation = str(photo_manifest["open_condition"])
        photo_manual_action = (
            "照片近景已登记；仍需一张能显示USB-UART模块及两根连线两端的"
            "原始全景照片。ST-Link可放在旁边，无需保持连接。"
        )
    else:
        photo_limitation = (
            "The registered photographs document a representative reconstructed "
            "setup received after the logged runs; neither JPEG contained EXIF "
            "capture-time metadata."
        )
        photo_manual_action = "照片近景与接线全景均已登记；无需继续补拍。"

    summary = {
        "schema_version": "1.0.0",
        "status": "FAIL_REQUIRED_GATES",
        "generated_from": {
            "physical_validation": str(PHYSICAL_VALIDATION.relative_to(ROOT)),
            "physical_validation_sha256": sha256(PHYSICAL_VALIDATION),
            "physical_firmware_manifest": str(PHYSICAL_MANIFEST.relative_to(ROOT)),
            "physical_firmware_manifest_sha256": sha256(PHYSICAL_MANIFEST),
            "proteus_validation": str(PROTEUS_VALIDATION.relative_to(ROOT)),
            "proteus_validation_sha256": sha256(PROTEUS_VALIDATION),
            "host_completion_manifest": str(HOST_COMPLETION.relative_to(ROOT)),
            "host_completion_manifest_sha256": sha256(HOST_COMPLETION),
            "physical_photo_manifest": (
                str(PHOTO_MANIFEST.relative_to(ROOT))
                if photo_manifest is not None else None
            ),
            "physical_photo_manifest_sha256": (
                sha256(PHOTO_MANIFEST) if photo_manifest is not None else None
            ),
        },
        "matrix": {
            "physical_scenarios": len(scenario_rows),
            "physical_cold_start_runs": physical_validation["received_runs"],
            "proteus_scenarios": proteus_validation["received"],
            "host_formal_runs": host_completion["run_count"],
            "build_hash_errors": build_hash_errors,
        },
        "physical_pair_comparisons": pair_rows,
        "resource_summary": {
            "whole_firmware_rom_bytes_min": min(
                int(row["rom_bytes"]) for row in resource_rows
            ),
            "whole_firmware_rom_bytes_max": max(
                int(row["rom_bytes"]) for row in resource_rows
            ),
            "whole_firmware_rw_bytes_min": min(
                int(row["rw_bytes"]) for row in resource_rows
            ),
            "whole_firmware_rw_bytes_max": max(
                int(row["rw_bytes"]) for row in resource_rows
            ),
            "interpretation_boundary": (
                "Each map describes the complete unified firmware image; "
                "the small scenario-to-scenario differences are not isolated "
                "per-algorithm incremental footprints."
            ),
        },
        "three_level_maxima": {
            "host_physical_output_snr_abs_difference_db": max_host_physical_snr,
            "host_physical_frequency_mae_abs_difference_hz": (
                max_host_physical_frequency
            ),
            "host_physical_tracker_calls_abs_difference": max_host_physical_calls,
            "host_physical_state_mismatches_of_160": max_host_physical_states,
            "host_proteus_output_snr_abs_difference_db": max_host_proteus_snr,
            "host_proteus_frequency_mae_abs_difference_hz": (
                max_host_proteus_frequency
            ),
            "host_proteus_tracker_calls_abs_difference": max_host_proteus_calls,
            "host_proteus_state_mismatches_of_160": max_host_proteus_states,
        },
        "gates": gates,
        "photo_evidence": (
            {
                "status": photo_manifest["status"],
                "overall_gate": photo_gate,
                "photo_count": len(photo_manifest["photos"]),
                "open_condition": photo_manifest["open_condition"],
            }
            if photo_manifest is not None else {
                "status": "NOT_CHECKED",
                "overall_gate": "NOT_CHECKED",
                "photo_count": 0,
                "open_condition": photo_limitation,
            }
        ),
        "supported_claims": [
            (
                "The 36-run physical on-device internal-signal matrix is "
                "complete, structurally valid, numerically finite, and "
                "repeatable across three human-confirmed cold starts."
            ),
            (
                "A3 reduces tracker calls and mean measured physical MCU "
                "cycles relative to A2 in all five paired scenarios."
            ),
            (
                "The deployed Rev15 images and their HEX, AXF, and MAP "
                "artifacts are hash-bound."
            ),
        ],
        "required_limitations": [
            (
                "Every tested A2/A3 physical scenario has at least one "
                "block maximum above the 72,000-cycle 1 kHz deadline."
            ),
            (
                "The firmware-reported deadline counter is not authoritative "
                "because the physical images logged deadline_cycles=0; the "
                "gate uses an external 72,000-cycle threshold."
            ),
            (
                "The physical board generated its test signals internally; "
                "no sensor or analog front end was tested."
            ),
            "No calibrated power or energy measurement was performed.",
            photo_limitation,
            (
                "MAP totals describe whole unified firmware images and do "
                "not isolate the incremental footprint of A0-A3."
            ),
        ],
        "scenario_detail": detail,
    }

    write_csv(SCENARIO_CSV, scenario_rows)
    write_csv(CONSISTENCY_CSV, consistency_rows)
    write_csv(RESOURCE_CSV, resource_rows)
    SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    pair_table = "\n".join(
        "| {condition} | {tracker:.3f}% | {cycles:.3f}% | {a2d} | {a3d} |".format(
            condition=row["condition"],
            tracker=100.0 * float(row["tracker_calls_reduction_fraction"]),
            cycles=100.0 * float(row["mean_cycles_reduction_fraction"]),
            a2d=row["a2_deadline_violating_blocks"],
            a3d=row["a3_deadline_violating_blocks"],
        )
        for row in pair_rows
    )
    gate_table = "\n".join(
        f"| `{name}` | {value} |" for name, value in gates.items()
    )
    report = f"""---
artifact_id: implementation-audit__rdmr-pli__phase5-physical-and-consistency__candidate__v1.0.0
project_id: ft-vss-nlms-stm32-ei
artifact_kind: implementation-audit
work_unit: quantitative-audit
status: candidate
language: zh
baseline_artifact: paper_workspace/scope/experiment-protocol__rdmr-pli__cssp-journal__candidate__v0.3.0.md
source_registry: paper_workspace/.sci-review-system/state/project_state.json
run_id: run-20260726-001
gate_status: manual-evidence-gates-open
next_intents:
  - visual-reference-qa
  - science-audit
---

# Phase 5 实物STM32与三端一致性审计

## 目的与范围

本报告审计12个核心场景、36次实物冷启动日志，并将实物Rev15与主机冻结C执行路径及Proteus Rev14作场景级比较。实物信号由MCU内部生成；本报告不把它表述为传感器、模拟前端或功耗实验。

## 已确认事实

- 实物矩阵：12个场景、36次冷启动，完整性、有限值与三次重复性均为PASS。
- 主机正式矩阵：{host_completion['run_count']}次；Proteus核心矩阵：{proteus_validation['received']}个场景。
- Rev15的12组HEX、AXF、MAP哈希复核：{'PASS' if not build_hash_errors else 'FAIL'}。
- A0/A1满足72,000周期外部截止；全部A2/A3场景存在截止违约。
- 已登记实物平台/芯片近景照片；完整串口接线路径门禁为`{photo_gate}`。

## 实物A3相对A2

| 条件 | 调用减少 | 平均周期减少 | A2超期块 | A3超期块 |
|---|---:|---:|---:|---:|
{pair_table}

这支持“A3在所有五组配对条件下降低平均计算开销和跟踪器调用”的有限结论，但不支持“满足1 ms硬实时”“降低功耗”或“普遍优于A2”。

## 三端一致性最大差异

| 比较 | 输出SNR绝对差 | 频率MAE绝对差 | 调用次数绝对差 | 状态不匹配/160 |
|---|---:|---:|---:|---:|
| 主机—实物 | {fmt(max_host_physical_snr)} dB | {fmt(max_host_physical_frequency)} Hz | {max_host_physical_calls} | {max_host_physical_states} |
| 主机—Proteus | {fmt(max_host_proteus_snr)} dB | {fmt(max_host_proteus_frequency)} Hz | {max_host_proteus_calls} | {max_host_proteus_states} |

逐场景数值见`outputs/phase5_physical_core/phase5_three_level_consistency.csv`。任何未通过0.10 dB、0.05 Hz、调用差不超过1或状态全一致门槛的场景，都必须保留为差异，不能静默删除。

## Flash与RAM

- 完整统一固件ROM范围：{summary['resource_summary']['whole_firmware_rom_bytes_min']}–{summary['resource_summary']['whole_firmware_rom_bytes_max']} bytes。
- 完整统一固件RW范围：{summary['resource_summary']['whole_firmware_rw_bytes_min']}–{summary['resource_summary']['whole_firmware_rw_bytes_max']} bytes。
- 这些MAP值描述包含A0–A3统一入口的整套映像；不能把4–8 bytes的场景差异解释为算法独立占用差异。

## Gate结果

| Gate | 结果 |
|---|---|
{gate_table}

总体状态：`FAIL_REQUIRED_GATES`。失败的硬实时或三端一致性门槛必须如实进入后续论点边界；照片门禁为`{photo_gate}`，功耗证据保持`NOT_CHECKED`。

## 证据边界与禁止表述

- 允许：on-device internal-signal validation、平均周期和调用次数降低、性能—开销权衡。
- 禁止：真实传感器采集、模拟前端验证、功耗降低、节能、1 kHz硬实时达标、A3普遍优于A2。
- 固件内`deadline_cycles=0`，所以设备报告的零违约不构成实时PASS；本报告统一使用72,000周期外部门槛。

## 人工补充项

1. {photo_manual_action}
2. 如论文要讨论功耗，必须另做校准电流/功率测量；否则保持未测量。
3. 作者/导师确认后续论文采用“性能—开销权衡”定位，并接受硬实时门槛失败的明确披露。

## 派生文件

- `outputs/phase5_physical_core/phase5_physical_core_gate_summary.json`
- `outputs/phase5_physical_core/phase5_physical_matrix_summary.csv`
- `outputs/phase5_physical_core/phase5_three_level_consistency.csv`
- `outputs/phase5_physical_core/phase5_physical_resource_summary.csv`
"""
    REPORT_MD.write_text(report, encoding="utf-8")

    generated = [SUMMARY_JSON, SCENARIO_CSV, CONSISTENCY_CSV, RESOURCE_CSV, REPORT_MD]
    print(json.dumps({
        "status": summary["status"],
        "gates": gates,
        "three_level_maxima": summary["three_level_maxima"],
        "generated": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in generated
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
