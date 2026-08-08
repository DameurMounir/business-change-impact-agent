#!/usr/bin/env python3
"""Verify public numeric claims against committed generated results."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    result = json.loads(
        (ROOT / "evaluation" / "results" / "rule-baseline.json").read_text(encoding="utf-8")
    )
    answer = json.loads((ROOT / "evaluation" / "answer-key.json").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    expected = answer["expected_summary"]
    phrases = {
        "direct": f"**{expected['direct']}**",
        "indirect": f"**{expected['indirect']}**",
        "conditional": f"**{expected['conditional']}**",
        "explicitly_unaffected": f"**{expected['explicitly_unaffected']}**",
        "collisions": f"**{expected['collisions']}**",
        "blocked_candidates": f"**{expected['blocked_candidates']}**",
    }
    missing = [name for name, phrase in phrases.items() if phrase not in readme]
    if missing:
        print(f"README numeric claims missing or stale: {missing}")
        return 1
    if result["deterministic_contract_correct"] is not True:
        print("public release cannot claim a correct frozen-case contract")
        return 1
    required = [
        "not general model accuracy",
        "Live-model evaluation is `NOT_RUN`",
        "does **not** execute change",
        "not a captured production screen",
    ]
    absent = [text for text in required if text not in readme]
    if absent:
        print(f"README claim boundaries missing: {absent}")
        return 1
    print("PASS: README numeric observations and claim boundaries verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
