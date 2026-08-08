#!/usr/bin/env python3
"""Copy the frozen case and rule files into the installable package."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "business_change_impact_agent"


def copy_assets(destination: Path) -> None:
    sample_case = destination / "sample_case"
    rules = destination / "rules"
    if sample_case.exists():
        shutil.rmtree(sample_case)
    if rules.exists():
        shutil.rmtree(rules)
    shutil.copytree(ROOT / "cases" / "atlasbridge", sample_case)
    rules.mkdir(parents=True)
    for source in sorted((ROOT / "design").glob("*.json")):
        shutil.copy2(source, rules / source.name)


def tree(path: Path) -> dict[str, bytes]:
    return {item.relative_to(path).as_posix(): item.read_bytes() for item in sorted(path.rglob("*")) if item.is_file()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="bcia-package-assets-") as temporary:
            generated = Path(temporary)
            copy_assets(generated)
            expected = tree(generated)
            actual = {}
            for folder in [PACKAGE / "sample_case", PACKAGE / "rules"]:
                for item in sorted(folder.rglob("*")):
                    if item.is_file():
                        actual[item.relative_to(PACKAGE).as_posix()] = item.read_bytes()
            if expected != actual:
                print("packaged case or rule assets drifted")
                return 1
        print("PASS: packaged case and rule assets are byte-stable")
        return 0
    copy_assets(PACKAGE)
    print("PASS: synchronized package case and rule assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
