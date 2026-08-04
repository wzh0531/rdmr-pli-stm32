"""Validate all Phase-4 artifacts and generate grouped summaries."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "phase4_host"
MANIFEST = OUT / "phase4_completion_manifest.json"
METRICS = OUT / "phase4_run_metrics.csv"
STATS = OUT / "phase4_paired_statistics.json"
REPORT = OUT / "phase4_validation_and_grouped_summary.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def summarize(groups: dict[tuple, list[float]]) -> list[dict[str, object]]:
    output = []
    for key, values in sorted(groups.items()):
        array = np.asarray(values, dtype=np.float64)
        output.append({
            "group": list(key), "count": array.size,
            "mean": float(array.mean()),
            "sd": float(array.std(ddof=1)) if array.size > 1 else 0.0,
            "median": float(np.median(array)),
            "iqr": [float(x) for x in np.quantile(array, [0.25, 0.75])],
        })
    return output


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest["status"] != "PASS":
        errors.append("completion manifest status is not PASS")
    if sha256(METRICS) != manifest["metrics_csv_sha256"]:
        errors.append("metrics CSV hash mismatch")
    if sha256(STATS) != manifest["statistics_json_sha256"]:
        errors.append("statistics JSON hash mismatch")
    if len(manifest["batch_archives"]) != 66:
        errors.append("expected 66 batch archives")

    archive_checks = []
    for relative, expected in manifest["batch_archives"].items():
        path = ROOT / relative
        actual = sha256(path)
        item_errors = []
        if actual != expected:
            item_errors.append("hash")
        with np.load(path, allow_pickle=False) as data:
            expected_shapes = {
                "input": (30, 8000), "clean": (30, 8000),
                "true_frequency": (30, 8000),
                "output": (4, 30, 8000),
                "estimated_frequency": (4, 30, 8000),
                "residual_ratio": (4, 30, 8000),
                "tracker_calls": (4, 30, 8000),
                "state": (4, 30, 8000),
            }
            for name, shape in expected_shapes.items():
                if data[name].shape != shape:
                    item_errors.append(f"{name}_shape")
                if name not in {"tracker_calls", "state"} and not np.isfinite(
                    data[name]
                ).all():
                    item_errors.append(f"{name}_finite")
            if not np.isin(data["state"], [0, 1, 2, 3]).all():
                item_errors.append("state_range")
        if item_errors:
            errors.append(f"{relative}: {item_errors}")
        archive_checks.append({
            "path": relative, "sha256": actual,
            "status": "PASS" if not item_errors else "FAIL",
        })

    with METRICS.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 7920:
        errors.append(f"run rows {len(rows)} != 7920")
    if any(row["status"] != "PASS" for row in rows):
        errors.append("failed run present")
    main_rows = [row for row in rows if row["matrix"] == "main"]
    near_rows = [row for row in rows if row["matrix"] == "near"]
    if len(main_rows) != 6480 or len(near_rows) != 1440:
        errors.append("matrix row counts differ from 6480/1440")
    if sorted({int(row["seed"]) for row in rows}) != list(range(1000, 1030)):
        errors.append("frozen test seed set mismatch")

    main_snr: dict[tuple, list[float]] = defaultdict(list)
    main_frequency: dict[tuple, list[float]] = defaultdict(list)
    near_snr: dict[tuple, list[float]] = defaultdict(list)
    near_42: dict[tuple, list[float]] = defaultdict(list)
    near_58: dict[tuple, list[float]] = defaultdict(list)
    for row in main_rows:
        key = (
            int(row["algorithm"]), row["trajectory"],
            float(row["pli_amplitude"]), int(row["noise"]),
        )
        main_snr[key].append(float(row["output_snr_db"]))
        main_frequency[key].append(float(row["frequency_mae_hz"]))
    for row in near_rows:
        key = (
            int(row["algorithm"]), row["near_line"],
            float(row["pli_amplitude"]),
        )
        near_snr[key].append(float(row["output_snr_db"]))
        near_42[key].append(float(row["f42_amplitude_error"]))
        near_58[key].append(float(row["f58_amplitude_error"]))

    result = {
        "schema_version": "1.0.0",
        "status": "PASS" if not errors else "FAIL",
        "manifest_sha256": sha256(MANIFEST),
        "run_counts": {
            "main": len(main_rows), "near": len(near_rows),
            "ablation_reused": manifest["ablation_run_count_reused"],
        },
        "archive_count": len(archive_checks),
        "archive_checks": archive_checks,
        "group_key_definitions": {
            "main": ["algorithm", "trajectory", "pli_amplitude", "noise"],
            "near": ["algorithm", "near_line", "pli_amplitude"],
        },
        "main_output_snr": summarize(main_snr),
        "main_frequency_mae": summarize(main_frequency),
        "near_output_snr": summarize(near_snr),
        "near_f42_amplitude_error": summarize(near_42),
        "near_f58_amplitude_error": summarize(near_58),
        "paired_statistics": json.loads(STATS.read_text(encoding="utf-8")),
        "errors": errors,
    }
    REPORT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"], "errors": errors,
        "runs": result["run_counts"], "archives": len(archive_checks),
    }, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
