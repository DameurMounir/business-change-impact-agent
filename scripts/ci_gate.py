#!/usr/bin/env python3
"""A milestone-safe CI gate used before the final release gate exists."""

from __future__ import annotations

import compileall
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    if not compileall.compile_dir(ROOT / "src", quiet=1):
        return 1
    conditional_commands = [
        ("scripts/build_case.py", [sys.executable, "scripts/build_case.py", "--check"]),
        ("scripts/verify_case.py", [sys.executable, "scripts/verify_case.py"]),
        (
            "scripts/generate_contracts.py",
            [sys.executable, "scripts/generate_contracts.py", "--check"],
        ),
        (
            "scripts/sync_package_assets.py",
            [sys.executable, "scripts/sync_package_assets.py", "--check"],
        ),
        ("scripts/evaluate.py", [sys.executable, "scripts/evaluate.py", "--check"]),
        (
            "scripts/generate_public_artifacts.py",
            [sys.executable, "scripts/generate_public_artifacts.py", "--check"],
        ),
        (
            "scripts/verify_public_claims.py",
            [sys.executable, "scripts/verify_public_claims.py"],
        ),
    ]
    for relative_path, command in conditional_commands:
        if (ROOT / relative_path).exists():
            run(command)
    if (ROOT / "tests").exists():
        run([sys.executable, "-m", "pytest", "-q", "--no-cov"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
