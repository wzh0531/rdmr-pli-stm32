"""Create the hash-bound manifest for the 12 physical-F103 Rev15 binaries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "firmware" / "stm32_keil" / "build"
OUT = ROOT / "outputs" / "phase5_physical_core"
MANIFEST = OUT / "phase5_physical_core_firmware_manifest.json"
PROTEUS_MANIFEST = (
    ROOT / "outputs" / "phase5_proteus_core"
    / "phase5_proteus_core_firmware_manifest.json"
)
SEED = 20260727
SCENARIOS = [
    (501, "P1", "A0", "F1", "0.50", "050"),
    (502, "P1", "A1", "F1", "0.50", "050"),
    (503, "P1", "A2", "F1", "0.50", "050"),
    (504, "P1", "A3", "F1", "0.50", "050"),
    (505, "P2", "A2", "F2", "0.20", "020"),
    (506, "P2", "A3", "F2", "0.20", "020"),
    (507, "P2", "A2", "F2", "0.50", "050"),
    (508, "P2", "A3", "F2", "0.50", "050"),
    (509, "P2", "A2", "F2", "1.00", "100"),
    (510, "P2", "A3", "F2", "1.00", "100"),
    (511, "P3", "A2", "F3", "0.50", "050"),
    (512, "P3", "A3", "F3", "0.50", "050"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def map_sizes(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    labels = {
        "ro_bytes": r"Total RO\s+Size.*?\s(\d+)\s+\(",
        "rw_bytes": r"Total RW\s+Size.*?\s(\d+)\s+\(",
        "rom_bytes": r"Total ROM Size.*?\s(\d+)\s+\(",
    }
    values = {}
    for key, pattern in labels.items():
        match = re.search(pattern, text)
        if match is None:
            raise RuntimeError(f"Cannot parse {key} from {path}")
        values[key] = int(match.group(1))
    return values


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "logs").mkdir(parents=True, exist_ok=True)
    (OUT / "photos").mkdir(parents=True, exist_ok=True)
    records = []
    for scenario_id, group, algorithm, trajectory, amplitude, amp_tag in SCENARIOS:
        stem = (
            f"PHASE5_PHYSICAL_{group}_S{scenario_id}_{algorithm}_"
            f"{trajectory}_P{amp_tag}_Z20_REV15"
        )
        paths = {
            suffix: BUILD / f"{stem}.{suffix}"
            for suffix in ("hex", "axf", "map")
        }
        missing = [str(path) for path in paths.values() if not path.is_file()]
        if missing:
            raise RuntimeError(f"Missing physical artifacts: {missing}")
        algorithm_id = int(algorithm[1])
        records.append({
            "scenario_id": scenario_id,
            "group": group,
            "algorithm": algorithm,
            "algorithm_id": algorithm_id,
            "trajectory": trajectory,
            "trajectory_id": int(trajectory[1]),
            "pli_amplitude": float(amplitude),
            "pli_amplitude_u6": int(float(amplitude) * 1_000_000),
            "noise": "snr20",
            "noise_id": 1,
            "near_line": "N0",
            "near_line_id": 0,
            "seed": SEED,
            "cold_start_count": 3,
            "expected_sample_count": 8000,
            "expected_block_rows": 160,
            "expected_final_tracker_calls": (
                0 if algorithm_id < 2 else (160 if algorithm_id == 2 else None)
            ),
            "log_filename_pattern": f"{stem}_COLD{{cold_start:02d}}.txt",
            "artifacts": {
                suffix: {
                    "path": str(path.relative_to(ROOT)),
                    "sha256": sha256(path),
                    "bytes": path.stat().st_size,
                }
                for suffix, path in paths.items()
            },
            "memory": map_sizes(paths["map"]),
        })
    result = {
        "schema_version": "1.0.0",
        "status": "candidate-awaiting-physical-logs",
        "protocol_id": "cssp-rdmr-pli-v0.3.0",
        "implementation_version": "0.3.2",
        "firmware_revision": 15,
        "target": "STM32F103C8T6 physical board",
        "compiler": "ARMCC, Cortex-M3, C99, -O2, split_sections",
        "clock_contract": {
            "hse_hz": 8_000_000,
            "pll_multiplier": 9,
            "core_hz": 72_000_000,
            "apb2_hz": 72_000_000,
            "uart_baud": 115_200,
            "usart1_brr": "0x271",
        },
        "platform_delta_from_rev14_proteus": {
            "algorithm_or_frozen_parameter_changed": False,
            "proteus_clock_model_disabled": True,
            "physical_hse_pll_enabled": True,
            "uart_brr_changed_from_0x4E_to_0x271": True,
            "log_schema_changed": False,
        },
        "parent_proteus_manifest": {
            "path": str(PROTEUS_MANIFEST.relative_to(ROOT)),
            "sha256": sha256(PROTEUS_MANIFEST),
        },
        "freeze_manifest_sha256": sha256(
            ROOT / "config/tuned-parameters__rdmr-pli__phase3__frozen__v1.0.0.json"
        ),
        "build_script_sha256": sha256(
            ROOT / "firmware/stm32_keil/build_armcc.ps1"
        ),
        "scenario_build_script_sha256": sha256(
            ROOT / "firmware/stm32_keil/build_phase5_physical_core.ps1"
        ),
        "scenario_count": len(records),
        "expected_device_runs": len(records) * 3,
        "scenarios": records,
        "evidence_boundary": {
            "binaries_built": True,
            "physical_logs_received": False,
            "physical_mcu_cycles_checked": False,
            "power_or_energy_checked": False,
        },
    }
    MANIFEST.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "PASS",
        "scenario_count": len(records),
        "expected_device_runs": len(records) * 3,
        "manifest": str(MANIFEST),
        "manifest_sha256": sha256(MANIFEST),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
