#!/usr/bin/env python3
"""Fail closed on secrets, private evidence and evaluator leakage."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".json", ".txt", ".svg", ".html", ".ini"}
FORBIDDEN_NAMES = {".env", "id_rsa", "id_ed25519"}
PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(r"\bgh[oprsu]_[A-Za-z0-9_]{30,}\b"),
    "openai-token": re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private-home-path": re.compile(r"/home/" + "dameur" + "mounir/"),
}


def main() -> int:
    findings: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or ".git" in path.parts or ".venv" in path.parts:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if path.name in FORBIDDEN_NAMES or path.suffix.lower() in {
            ".pem",
            ".key",
            ".p12",
            ".sqlite3",
        }:
            findings.append(f"forbidden file: {relative}")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{label}: {relative}")
        if relative.startswith("src/") and ("answer-key" in text or "answer_key" in text):
            findings.append(f"evaluator boundary leakage: {relative}")
    if findings:
        print("PUBLIC_BOUNDARY_BLOCKED")
        for finding in findings:
            print("-", finding)
        return 1
    print("PASS: synthetic public boundary and secret patterns verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
