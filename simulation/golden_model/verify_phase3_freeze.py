"""Verify the Phase-3 freeze manifest and reject silent changes."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    ROOT
    / "config"
    / "tuned-parameters__rdmr-pli__phase3__frozen__v1.0.0.json"
)
REPORT = ROOT / "outputs" / "phase3_freeze" / "freeze_validation.json"

HASH_PATHS = {
    "frozen_protocol_markdown": (
        "paper_workspace/scope/"
        "experiment-protocol__rdmr-pli__cssp-journal__candidate__v0.3.0.md"
    ),
    "machine_protocol_json": (
        "config/experiment_protocol__rdmr-pli__v0.3.0.json"
    ),
    "tuning_space_json": (
        "config/tuning-space__rdmr-pli__phase3__candidate__v0.1.0.json"
    ),
    "candidate_runs_csv": (
        "outputs/phase3_tuning/phase3_candidate_runs.csv"
    ),
    "candidate_summary_csv": (
        "outputs/phase3_tuning/phase3_candidate_summary.csv"
    ),
    "tuning_result_json": (
        "outputs/phase3_tuning/phase3_tuning_result.json"
    ),
    "seed_access_audit_json": (
        "outputs/phase3_tuning/phase3_seed_access_audit.json"
    ),
    "rdmr_pli_c": "firmware/core/rdmr_pli.c",
    "rdmr_pli_h": "firmware/core/rdmr_pli.h",
    "formal_algorithms_py": "simulation/golden_model/formal_algorithms.py",
    "rdmr_experiment_config_h": (
        "firmware/core/rdmr_experiment_config.h"
    ),
    "stm32_main_c": "firmware/stm32_keil/App/main.c",
    "phase3_tuning_runner_py": (
        "simulation/golden_model/run_phase3_tuning.py"
    ),
    "phase3_host_case_c": "firmware/host_test/phase3_tuning_case.c",
    "phase3_alignment_report_json": (
        "outputs/phase3_freeze/algorithm_alignment_report_rev14.json"
    ),
    "a3_rev14_hex": (
        "firmware/stm32_keil/build/"
        "USE_THIS_A3_PHASE3_FROZEN_REV14.hex"
    ),
    "a3_rev14_axf": (
        "firmware/stm32_keil/build/"
        "USE_THIS_A3_PHASE3_FROZEN_REV14.axf"
    ),
    "a3_rev14_map": (
        "firmware/stm32_keil/build/"
        "USE_THIS_A3_PHASE3_FROZEN_REV14.map"
    ),
    "phase3_freeze_verifier_py": (
        "simulation/golden_model/verify_phase3_freeze.py"
    ),
}

NONPUBLIC_HASH_KEYS = {"frozen_ei_draft"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def parameter_fingerprint(parameters: dict[str, object]) -> str:
    payload = json.dumps(
        parameters,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest().upper()


def require_pattern(
    errors: list[str],
    text: str,
    pattern: str,
    label: str,
) -> None:
    if re.search(pattern, text, flags=re.MULTILINE) is None:
        errors.append(f"selected parameter/version missing in {label}")


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors: list[str] = []
    actual_hashes: dict[str, str] = {}
    expected_hashes = manifest["hashes_sha256"]

    public_expected_hashes = {
        key: value
        for key, value in expected_hashes.items()
        if key not in NONPUBLIC_HASH_KEYS
    }
    if set(public_expected_hashes) != set(HASH_PATHS):
        missing = sorted(set(HASH_PATHS) - set(expected_hashes))
        unexpected = sorted(set(public_expected_hashes) - set(HASH_PATHS))
        errors.append(
            f"manifest hash key mismatch; missing={missing}, "
            f"unexpected={unexpected}"
        )
    for key, relative_path in HASH_PATHS.items():
        path = ROOT / relative_path
        if not path.is_file():
            errors.append(f"missing frozen artifact: {relative_path}")
            continue
        actual = sha256(path)
        actual_hashes[key] = actual
        expected = public_expected_hashes.get(key)
        if actual != expected:
            errors.append(
                f"hash mismatch {key}: expected={expected}, actual={actual}"
            )

    parameters = manifest["parameters"]
    actual_fingerprint = parameter_fingerprint(parameters)
    if actual_fingerprint != manifest["parameter_fingerprint_sha256"]:
        errors.append("parameter fingerprint mismatch")

    header = (ROOT / "firmware/core/rdmr_pli.h").read_text(
        encoding="utf-8"
    )
    formal = (
        ROOT / "simulation/golden_model/formal_algorithms.py"
    ).read_text(encoding="utf-8")
    experiment = (
        ROOT / "firmware/core/rdmr_experiment_config.h"
    ).read_text(encoding="utf-8")
    require_pattern(
        errors,
        header,
        r"#define\s+RDMR_BLOCK_SIZE\s+50U",
        "rdmr_pli.h",
    )
    require_pattern(
        errors,
        header,
        r"#define\s+RDMR_INTERVAL_FAST\s+1U",
        "rdmr_pli.h",
    )
    require_pattern(
        errors,
        header,
        r"#define\s+RDMR_INTERVAL_MID\s+3U",
        "rdmr_pli.h",
    )
    require_pattern(
        errors,
        header,
        r"#define\s+RDMR_INTERVAL_SLOW\s+12U",
        "rdmr_pli.h",
    )
    require_pattern(
        errors,
        header,
        r"#define\s+RDMR_RESIDUAL_NEW_WEIGHT\s+0\.30f",
        "rdmr_pli.h",
    )
    require_pattern(
        errors,
        header,
        r"#define\s+RDMR_THRESHOLD_SCALE\s+1\.0f",
        "rdmr_pli.h",
    )
    require_pattern(
        errors,
        formal,
        r"RESIDUAL_NEW_WEIGHT\s*=\s*F32\(0\.30\)",
        "formal_algorithms.py",
    )
    require_pattern(
        errors,
        experiment,
        r'RDMR_IMPLEMENTATION_VERSION\s+"0\.3\.2"',
        "rdmr_experiment_config.h",
    )
    require_pattern(
        errors,
        experiment,
        r"RDMR_FIRMWARE_REVISION\s+14U",
        "rdmr_experiment_config.h",
    )

    candidate_path = ROOT / HASH_PATHS["candidate_runs_csv"]
    with candidate_path.open(newline="", encoding="utf-8") as handle:
        candidate_rows = list(csv.DictReader(handle))
    evaluated_seeds = sorted({int(row["seed"]) for row in candidate_rows})
    if len(candidate_rows) != 360:
        errors.append(
            f"candidate row count changed: {len(candidate_rows)} != 360"
        )
    if evaluated_seeds != list(range(100, 110)):
        errors.append(f"unexpected evaluated seeds: {evaluated_seeds}")
    if set(evaluated_seeds) & set(range(1000, 1030)):
        errors.append("frozen test seed found in candidate runs")

    result = {
        "schema_version": "1.0.0",
        "status": "PASS" if not errors else "FAIL",
        "freeze_id": manifest["freeze_id"],
        "manifest_sha256": sha256(MANIFEST),
        "parameter_fingerprint_expected": (
            manifest["parameter_fingerprint_sha256"]
        ),
        "parameter_fingerprint_actual": actual_fingerprint,
        "hashes_checked": len(actual_hashes),
        "candidate_rows_checked": len(candidate_rows),
        "evaluated_seeds": evaluated_seeds,
        "frozen_test_seed_overlap": sorted(
            set(evaluated_seeds) & set(range(1000, 1030))
        ),
        "errors": errors,
        "actual_hashes_sha256": actual_hashes,
        "nonpublic_hashes_not_checked": sorted(NONPUBLIC_HASH_KEYS),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
