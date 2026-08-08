#!/usr/bin/env python3
"""Inspect wheel and source distribution contents."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

FORBIDDEN_PARTS = {
    "evaluation",
    "tests",
    "docs",
    "artifacts",
    "runs",
    "exports",
    "__pycache__",
    ".git",
}
FORBIDDEN_NAMES = {".env", "answer-key.json", "answer-key.sha256"}


def _validate(names: list[str], archive: Path) -> None:
    normalised: list[PurePosixPath] = []
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"unsafe archive path in {archive}: {name}")
        normalised.append(path)
        if any(part in FORBIDDEN_PARTS for part in path.parts) or path.name in FORBIDDEN_NAMES:
            raise SystemExit(f"forbidden packaged path in {archive}: {name}")
        if path.suffix in {".pyc", ".sqlite3", ".pem", ".key"}:
            raise SystemExit(f"forbidden packaged file in {archive}: {name}")
    joined = [path.as_posix() for path in normalised]
    required_suffixes = [
        "business_change_impact_agent/sample_case/manifest.json",
        "business_change_impact_agent/rules/propagation-rules.json",
        "business_change_impact_agent/py.typed",
    ]
    for suffix in required_suffixes:
        if not any(name.endswith(suffix) for name in joined):
            raise SystemExit(f"required package content missing from {archive}: {suffix}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    args = parser.parse_args()
    archives = sorted(args.dist.glob("*"))
    if len(archives) != 2:
        raise SystemExit(
            f"expected exactly one wheel and one source distribution, found {len(archives)}"
        )
    for archive in archives:
        if archive.suffix == ".whl":
            with zipfile.ZipFile(archive) as handle:
                bad = handle.testzip()
                if bad:
                    raise SystemExit(f"corrupt wheel entry: {bad}")
                _validate(handle.namelist(), archive)
        elif archive.name.endswith(".tar.gz"):
            with tarfile.open(archive, "r:gz") as handle:
                _validate(handle.getnames(), archive)
        else:
            raise SystemExit(f"unexpected distribution: {archive}")
    print("PASS: wheel and source distribution contents verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
