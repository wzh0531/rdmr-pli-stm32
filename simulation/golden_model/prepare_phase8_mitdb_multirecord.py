"""Freeze MIT-BIH record, lead, and segment selection before Phase-8 analysis."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = (
    ROOT
    / "sources"
    / "physionet_mitdb_1.0.0"
    / "mit-bih-arrhythmia-database-1.0.0"
)
ZIP_PATH = ROOT / "sources" / "mit-bih-arrhythmia-database-1.0.0.zip"
OUT = ROOT / "outputs" / "phase8_realtime_strengthening" / "mitdb_multirecord"
SEGMENT_START_SECONDS = (300, 900, 1500)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def parse_header(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="ascii").splitlines()
    first = lines[0].split()
    record = first[0]
    channels = int(first[1])
    sample_rate = int(float(first[2]))
    sample_count = int(first[3])
    signal_lines = [lines[index + 1].split() for index in range(channels)]
    leads = [tokens[-1] for tokens in signal_lines]
    selected_index = leads.index("MLII") if "MLII" in leads else 0
    selected = signal_lines[selected_index]
    return {
        "record": record,
        "subject_cluster": "subject_201_202" if record in {"201", "202"} else f"subject_{record}",
        "sample_rate_hz": sample_rate,
        "sample_count": sample_count,
        "channel_count": channels,
        "available_leads": leads,
        "selected_channel_zero_based": selected_index,
        "selected_lead": leads[selected_index],
        "selection_reason": "MLII preferred" if "MLII" in leads else "MLII unavailable; first header channel",
        "gain_adc_units_per_mv": float(selected[2].split("/")[0]),
        "adc_zero": float(selected[4]),
    }


def main() -> None:
    headers = sorted(
        path for path in SOURCE_ROOT.glob("*.hea")
        if path.stem.isdigit() and len(path.stem) == 3
    )
    if len(headers) != 48:
        raise RuntimeError(f"expected 48 top-level MIT-BIH headers, found {len(headers)}")
    records = []
    for header_path in headers:
        record = parse_header(header_path)
        data_path = SOURCE_ROOT / f"{header_path.stem}.dat"
        if not data_path.exists():
            raise RuntimeError(f"missing signal file: {data_path}")
        latest_end = (SEGMENT_START_SECONDS[-1] + 8) * int(record["sample_rate_hz"])
        if latest_end > int(record["sample_count"]):
            raise RuntimeError(f"record {header_path.stem} is too short for frozen segments")
        record["segments"] = [
            {"segment_index": index, "start_seconds": start, "duration_seconds": 8}
            for index, start in enumerate(SEGMENT_START_SECONDS)
        ]
        record["header_sha256"] = sha256(header_path)
        record["signal_sha256"] = sha256(data_path)
        records.append(record)

    manifest = {
        "schema_version": "1.0.0",
        "protocol": "rdmr-pli-realtime-strengthening-v0.5.0",
        "status": "FROZEN_BEFORE_ANALYSIS",
        "dataset": "MIT-BIH Arrhythmia Database v1.0.0",
        "dataset_doi": "10.13026/C2F305",
        "source_url": "https://physionet.org/content/mitdb/1.0.0/",
        "zip_sha256": sha256(ZIP_PATH),
        "record_count": len(records),
        "subject_cluster_count": len({record["subject_cluster"] for record in records}),
        "segment_start_seconds": list(SEGMENT_START_SECONDS),
        "lead_rule": "prefer exact MLII; otherwise use first header channel and record the lead",
        "injection_conditions_per_segment": 24,
        "algorithms": ["A2_hierarchical", "A3_hierarchical", "B4_hierarchical"],
        "records": records,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "selection_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": manifest["status"],
        "record_count": manifest["record_count"],
        "subject_cluster_count": manifest["subject_cluster_count"],
        "output": str(path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
