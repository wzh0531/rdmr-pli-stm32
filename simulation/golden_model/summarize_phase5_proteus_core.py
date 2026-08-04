"""Build the deterministic Phase-5 Proteus core-matrix gate summary."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "phase5_proteus_core"
VALIDATION = OUT / "phase5_proteus_log_validation.json"
P1 = OUT / "phase5_p1_a2_a3_pair_audit.json"
P2 = OUT / "phase5_p2_amplitude_pair_audit.json"
P3 = OUT / "phase5_p3_pair_audit.json"
REPORT = OUT / "phase5_proteus_core_gate_summary.json"


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def pair_record(
    label: str,
    a2: dict[str, object],
    a3: dict[str, object],
    comparison: dict[str, object],
    a2_scenario_id: int | None = None,
    a3_scenario_id: int | None = None,
) -> dict[str, object]:
    return {
        "pair": label,
        "a2_scenario_id": (
            a2_scenario_id
            if a2_scenario_id is not None else a2["scenario_id"]
        ),
        "a3_scenario_id": (
            a3_scenario_id
            if a3_scenario_id is not None else a3["scenario_id"]
        ),
        "a2_output_snr_db": a2["proteus_output_snr_db"],
        "a3_output_snr_db": a3["proteus_output_snr_db"],
        "a3_minus_a2_output_snr_db": comparison["output_snr_difference_db"],
        "a2_cycles_mean": a2["cycles_mean"],
        "a3_cycles_mean": a3["cycles_mean"],
        "mean_cycles_reduction_fraction": (
            comparison["mean_cycles_reduction_fraction"]
        ),
        "a2_tracker_calls": a2["proteus_final_tracker_calls"],
        "a3_tracker_calls": a3["proteus_final_tracker_calls"],
        "tracker_calls_reduction_fraction": (
            comparison["tracker_calls_reduction_fraction"]
        ),
        "a2_deadline_violations": a2["deadline_violations"],
        "a3_deadline_violations": a3["deadline_violations"],
        "a2_cycles_max": a2["cycles_max"],
        "a3_cycles_max": a3["cycles_max"],
        "a2_host_output_snr_difference_db": (
            a2["output_snr_absolute_difference_db"]
        ),
        "a3_host_output_snr_difference_db": (
            a3["output_snr_absolute_difference_db"]
        ),
        "a2_state_mismatches": a2["endpoint_state_mismatches"],
        "a3_state_mismatches": a3["endpoint_state_mismatches"],
        "a2_tracker_calls_host_difference": (
            a2["tracker_calls_absolute_difference"]
        ),
        "a3_tracker_calls_host_difference": (
            a3["tracker_calls_absolute_difference"]
        ),
    }


def main() -> None:
    validation = load(VALIDATION)
    p1 = load(P1)
    p2 = load(P2)
    p3 = load(P3)

    p1_by_algorithm = {
        row["algorithm"]: row for row in p1["per_algorithm"]
    }
    pairs = [
        pair_record(
            "P1-F1-P050",
            p1_by_algorithm["A2"],
            p1_by_algorithm["A3"],
            p1["a3_vs_a2"],
            503,
            504,
        )
    ]
    for pair in p2["pairs"]:
        by_algorithm = {
            row["algorithm"]: row for row in pair["per_algorithm"]
        }
        pairs.append(pair_record(
            f"P2-F2-{pair['pair']}",
            by_algorithm["A2"],
            by_algorithm["A3"],
            pair["a3_vs_a2"],
        ))
    p3_by_algorithm = {
        row["algorithm"]: row for row in p3["per_algorithm"]
    }
    pairs.append(pair_record(
        "P3-F3-P050",
        p3_by_algorithm["A2"],
        p3_by_algorithm["A3"],
        p3["a3_vs_a2"],
    ))

    cycle_reductions = [
        float(pair["mean_cycles_reduction_fraction"]) for pair in pairs
    ]
    call_reductions = [
        float(pair["tracker_calls_reduction_fraction"]) for pair in pairs
    ]
    snr_differences = [
        float(pair["a3_minus_a2_output_snr_db"]) for pair in pairs
    ]
    max_host_snr_difference = max(
        max(
            float(pair["a2_host_output_snr_difference_db"]),
            float(pair["a3_host_output_snr_difference_db"]),
        )
        for pair in pairs
    )
    max_state_mismatches = max(
        max(
            int(pair["a2_state_mismatches"]),
            int(pair["a3_state_mismatches"]),
        )
        for pair in pairs
    )

    result = {
        "schema_version": "1.0.0",
        "status": "FAIL_REQUIRED_GATES",
        "matrix": {
            "received_scenarios": validation["received"],
            "expected_scenarios": validation["expected"],
            "missing": validation["missing"],
            "integrity_failures": validation["integrity_failures"],
            "paired_a2_a3_comparisons": len(pairs),
        },
        "pair_comparisons": pairs,
        "aggregate": {
            "mean_cycles_reduction_fraction_min": min(cycle_reductions),
            "mean_cycles_reduction_fraction_max": max(cycle_reductions),
            "mean_cycles_reduction_fraction_mean": (
                sum(cycle_reductions) / len(cycle_reductions)
            ),
            "tracker_calls_reduction_fraction_min": min(call_reductions),
            "tracker_calls_reduction_fraction_max": max(call_reductions),
            "tracker_calls_reduction_fraction_mean": (
                sum(call_reductions) / len(call_reductions)
            ),
            "a3_minus_a2_output_snr_db_min": min(snr_differences),
            "a3_minus_a2_output_snr_db_max": max(snr_differences),
            "max_host_proteus_output_snr_difference_db": (
                max_host_snr_difference
            ),
            "max_endpoint_state_mismatches_of_160": max_state_mismatches,
        },
        "gates": {
            "all_12_scenarios_present": (
                "PASS"
                if validation["received"] == validation["expected"]
                and not validation["missing"] else "FAIL"
            ),
            "log_integrity": (
                "PASS" if not validation["integrity_failures"] else "FAIL"
            ),
            "numeric_faults": (
                "PASS"
                if all(
                    not result["errors"]
                    for result in validation["results"]
                ) else "FAIL"
            ),
            "a3_average_compute_lower_than_a2_all_pairs": (
                "PASS"
                if all(value > 0.0 for value in cycle_reductions) else "FAIL"
            ),
            "host_proteus_output_snr_le_0.10_db_all_pairs": (
                "PASS" if max_host_snr_difference <= 0.10 else "FAIL"
            ),
            "a3_state_sequence_matches_host_all_pairs": (
                "PASS" if max_state_mismatches == 0 else "FAIL"
            ),
            "hard_realtime_1khz_all_adaptive_scenarios": (
                "PASS"
                if not validation["realtime_failures"] else "FAIL"
            ),
            "physical_stm32_timing": "NOT_CHECKED",
            "power_or_energy": "NOT_CHECKED",
        },
        "supported_claims": [
            (
                "Proteus Rev14 evidence shows A3 reduces mean cycles and "
                "tracker calls relative to A2 in all five paired scenarios."
            ),
            (
                "P1 and P2 preserve closely matched A2/A3 output SNR under "
                "the tested conditions."
            ),
            (
                "All 12 logs are structurally complete and contain no "
                "reported numeric faults."
            ),
        ],
        "required_limitations": [
            (
                "The synchronous exhaustive tracker violates the 1 kHz "
                "worst-case deadline in every tested A2/A3 scenario."
            ),
            (
                "P3 A3 differs from the host reference by about 0.199 dB "
                "and has 13/160 endpoint state mismatches."
            ),
            (
                "Proteus DWT results are not physical STM32 timing, power, "
                "or energy measurements."
            ),
        ],
        "frozen_parameters_changed": False,
    }
    REPORT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
