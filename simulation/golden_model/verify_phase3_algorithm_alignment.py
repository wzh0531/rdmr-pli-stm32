"""Run C/Python algorithm alignment without overwriting Phase-2 evidence."""

from __future__ import annotations

from pathlib import Path

import verify_algorithm_alignment as alignment


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "outputs" / "phase3_freeze"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    alignment.OUTPUT_DIR = OUTPUT_DIR
    alignment.C_EXE = OUTPUT_DIR / "dump_algorithm_alignment_rev14.exe"
    alignment.C_CSV = OUTPUT_DIR / "c_algorithm_alignment_rev14.csv"
    alignment.PYTHON_CSV = (
        OUTPUT_DIR / "python_algorithm_alignment_rev14.csv"
    )
    alignment.REPORT = (
        OUTPUT_DIR / "algorithm_alignment_report_rev14.json"
    )
    alignment.main()


if __name__ == "__main__":
    main()
