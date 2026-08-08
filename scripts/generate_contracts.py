#!/usr/bin/env python3
"""Generate deterministic public JSON contracts from the typed model."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate(root: Path) -> None:
    schemas = root / "schemas"
    write_json(
        schemas / "analysis-result.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://github.com/DameurMounir/business-change-impact-agent/schemas/analysis-result.schema.json",
            "title": "Business Change Impact Analysis Result",
            "type": "object",
            "required": [
                "schema_version",
                "case_id",
                "case_digest",
                "decision_question",
                "adapter_id",
                "rulebook_digest",
                "maximum_depth",
                "impacts",
                "collisions",
                "summary",
                "authority_statement",
                "limitations",
                "analysis_digest"
            ],
            "properties": {
                "schema_version": {"const": "1.0.0"},
                "case_id": {"type": "string", "minLength": 1},
                "case_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "decision_question": {"const": "What changes directly and indirectly?"},
                "adapter_id": {"type": "string", "minLength": 1},
                "rulebook_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "maximum_depth": {"type": "integer", "minimum": 1, "maximum": 8},
                "impacts": {"type": "array", "items": {"$ref": "#/$defs/impact"}},
                "collisions": {"type": "array", "items": {"type": "object"}},
                "blocked_candidates": {"type": "array", "items": {"type": "object"}},
                "domain_heatmap": {"type": "object"},
                "summary": {"type": "object"},
                "authority_statement": {"type": "string", "minLength": 1},
                "limitations": {"type": "array", "items": {"type": "string"}},
                "analysis_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
            },
            "$defs": {
                "impact": {
                    "type": "object",
                    "required": [
                        "target_entity_id",
                        "classification",
                        "origin_change_ids",
                        "canonical_paths",
                        "evidence_refs",
                        "attention_tier",
                        "reason_codes",
                        "obligations"
                    ],
                    "properties": {
                        "target_entity_id": {"type": "string"},
                        "classification": {"enum": ["DIRECT", "INDIRECT", "CONDITIONAL", "EXPLICITLY_UNAFFECTED"]},
                        "origin_change_ids": {"type": "array", "items": {"type": "string"}},
                        "canonical_paths": {"type": "array", "items": {"type": "object"}},
                        "evidence_refs": {"type": "array", "items": {"type": "string"}},
                        "attention_tier": {"enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
                        "reason_codes": {"type": "array", "items": {"type": "string"}},
                        "obligations": {"type": "array", "items": {"type": "object"}}
                    }
                }
            },
            "additionalProperties": False
        },
    )
    write_json(
        schemas / "review-command.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://github.com/DameurMounir/business-change-impact-agent/schemas/review-command.schema.json",
            "title": "Digest-bound human review command",
            "type": "object",
            "required": ["run_id", "analysis_digest", "nonce", "reviewer", "action"],
            "properties": {
                "run_id": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$"},
                "analysis_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "nonce": {"type": "string", "minLength": 24, "maxLength": 256},
                "reviewer": {"type": "string", "minLength": 1, "maxLength": 120},
                "action": {"enum": ["CONFIRM", "REQUEST_REVISION", "EDIT", "REJECT"]},
                "comment": {"type": "string", "maxLength": 2000},
                "edits": {"type": "array", "maxItems": 50, "items": {"type": "object"}}
            },
            "additionalProperties": False
        },
    )


def digest_tree(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*.json"))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="bcia-contracts-") as temporary:
            generated = Path(temporary)
            generate(generated)
            expected = digest_tree(generated / "schemas")
            actual = digest_tree(SCHEMA_DIR)
            if expected != actual:
                print("generated contract drift detected")
                return 1
        print("PASS: generated contracts are byte-stable")
        return 0
    generate(ROOT)
    print("PASS: generated JSON contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
