from __future__ import annotations

import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SUMS = ROOT / "SHA256SUMS.txt"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def main() -> int:
    expected: dict[str, str] = {}
    for line in SUMS.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        expected[relative] = digest.lower()

    errors: list[str] = []
    for relative, digest in expected.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing: {relative}")
        elif sha256(path) != digest:
            errors.append(f"hash mismatch: {relative}")

    actual = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.relative_to(ROOT).parts
        and path.name != "SHA256SUMS.txt"
        and "__pycache__" not in path.relative_to(ROOT).parts
    }
    unlisted = sorted(actual - set(expected))
    stale = sorted(set(expected) - actual)
    errors.extend(f"unlisted: {item}" for item in unlisted)
    errors.extend(f"listed but absent: {item}" for item in stale)

    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print(f"PASS: {len(expected)} files verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
