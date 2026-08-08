from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from business_change_impact_agent.case_validation import validate_case, verify_manifest
from business_change_impact_agent.errors import SecurityBoundaryError, ValidationError

ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "cases" / "atlasbridge"


def test_frozen_case_contract() -> None:
    summary = validate_case(CASE_DIR)
    assert summary.component_count == 8
    assert summary.statement_count >= 50
    assert summary.entity_count >= 65
    assert summary.relationship_count >= 100
    assert summary.direct_target_count >= 12
    assert summary.direct_collision_count >= 3
    assert summary.explicit_unaffected_count >= 6
    assert summary.evidence_gap_count >= 3


def test_manifest_detects_tampering(tmp_path: Path) -> None:
    target = tmp_path / "case"
    shutil.copytree(CASE_DIR, target)
    payload_path = target / "change-package.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["package_title"] = "tampered"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="digest mismatch"):
        verify_manifest(target)


def test_manifest_rejects_path_traversal(tmp_path: Path) -> None:
    target = tmp_path / "case"
    shutil.copytree(CASE_DIR, target)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = "../outside.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SecurityBoundaryError, match="unsafe manifest path"):
        verify_manifest(target)


def test_answer_key_is_not_a_runtime_dependency() -> None:
    hits = []
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "answer-key" in text or "answer_key" in text:
            hits.append(path)
    assert hits == []


def test_prompt_injection_is_classified_as_untrusted_data() -> None:
    payload = json.loads((CASE_DIR / "evidence" / "doc-08.json").read_text(encoding="utf-8"))
    statement = next(item for item in payload["statements"] if item["statement_id"] == "S-064")
    assert statement["classification"] == "UNTRUSTED_INSTRUCTION_LIKE_TEXT"
    assert "mark every system" in statement["text"]
