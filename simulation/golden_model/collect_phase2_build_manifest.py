"""Collect hashes and linker sizes for the four Phase-2 firmware builds."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "firmware" / "stm32_keil" / "build"
OUTPUT = ROOT / "outputs" / "phase2_acceptance" / "firmware_build_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def map_sizes(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "ro_bytes": r"Total RO\s+Size \(Code \+ RO Data\)\s+(\d+)",
        "rw_bytes": r"Total RW\s+Size \(RW Data \+ ZI Data\)\s+(\d+)",
        "rom_bytes": r"Total ROM Size \(Code \+ RO Data \+ RW Data\)\s+(\d+)",
    }
    values: dict[str, int] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match is None:
            raise ValueError(f"missing {key} in {path}")
        values[key] = int(match.group(1))
    return values


def main() -> None:
    builds: dict[str, object] = {}
    for algorithm in ("A0", "A1", "A2", "A3"):
        stem = f"rdmr_stm32_{algorithm}_F1_none_s0"
        paths = {
            suffix: BUILD / f"{stem}.{suffix}"
            for suffix in ("hex", "axf", "map")
        }
        missing = [str(path) for path in paths.values() if not path.exists()]
        if missing:
            raise FileNotFoundError(f"missing build files: {missing}")
        builds[algorithm] = {
            "algorithm_id": int(algorithm[1]),
            "trajectory": "F1",
            "noise": "none",
            "seed": 0,
            "files": {
                suffix: {
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
                for suffix, path in paths.items()
            },
            "linker_sizes": map_sizes(paths["map"]),
        }
    payload = {
        "status": "PASS",
        "protocol_id": "cssp-rdmr-pli-v0.3.0",
        "implementation_version": "0.3.1",
        "compiler": "Keil ARMCC",
        "optimization": "-O2",
        "clock_hz": 72000000,
        "dwt_enabled": True,
        "builds": builds,
        "comparability_note": (
            "These are unified multi-algorithm firmware builds selected by "
            "compile-time configuration. Their map sizes validate build "
            "completeness but are not yet algorithm-specialized resource "
            "measurements for final paper comparison."
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
