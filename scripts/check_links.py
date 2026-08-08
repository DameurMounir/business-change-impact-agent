#!/usr/bin/env python3
"""Verify repository-relative Markdown links and image references."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def main() -> int:
    failures: list[str] = []
    checked = 0
    for markdown in sorted(ROOT.rglob("*.md")):
        if any(part in {".git", ".venv", "build", "dist"} for part in markdown.parts):
            continue
        text = markdown.read_text(encoding="utf-8")
        for raw in LINK.findall(text):
            target = raw.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_text = unquote(target.split("#", 1)[0])
            candidate = (markdown.parent / path_text).resolve()
            checked += 1
            if ROOT.resolve() not in candidate.parents and candidate != ROOT.resolve():
                failures.append(
                    f"link escapes repository: {markdown.relative_to(ROOT)} -> {target}"
                )
            elif not candidate.exists():
                failures.append(f"missing link target: {markdown.relative_to(ROOT)} -> {target}")
    if failures:
        print("LINK_CHECK_BLOCKED")
        for failure in failures:
            print("-", failure)
        return 1
    print(f"PASS: {checked} repository-relative Markdown links resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
