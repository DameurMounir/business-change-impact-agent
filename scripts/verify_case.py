#!/usr/bin/env python3
"""Verify the frozen AtlasBridge case and public-data boundary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from business_change_impact_agent.case_validation import validate_case  # noqa: E402


def main() -> int:
    summary = validate_case(ROOT / "cases" / "atlasbridge")
    answer_key = ROOT / "evaluation" / "answer-key.json"
    if not answer_key.is_file():
        raise SystemExit("missing evaluator-only answer key")
    payload = json.loads(answer_key.read_text(encoding="utf-8"))
    if payload.get("authorship") != "HUMAN_CURATED_EVALUATION_ONLY":
        raise SystemExit("answer key boundary marker is missing")
    runtime_hits = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "answer-key" in text or "answer_key" in text:
            runtime_hits.append(path.relative_to(ROOT).as_posix())
    if runtime_hits:
        raise SystemExit(f"runtime answer-key reference detected: {runtime_hits}")
    print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))
    print("PASS: case manifest, evidence, graph and evaluation boundary verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
