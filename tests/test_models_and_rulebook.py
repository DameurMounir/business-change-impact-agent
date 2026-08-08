from __future__ import annotations

import json
from pathlib import Path

import pytest

from business_change_impact_agent.case_loader import load_case
from business_change_impact_agent.domain import AttentionTier, ImpactClassification
from business_change_impact_agent.errors import ValidationError
from business_change_impact_agent.rulebook import attention_for, load_rulebook

ROOT = Path(__file__).resolve().parents[1]


def test_case_loader_binds_manifest_without_evaluator_material() -> None:
    case = load_case(ROOT / "cases" / "atlasbridge")
    assert case.case_id == "ATLASBRIDGE-ONBOARDING-IMPACT-001"
    assert len(case.components) == 8
    assert len(case.entities) == 77
    assert len(case.relationships) >= 165
    assert len(case.case_digest) == 64
    assert "S-064" in case.statements


def test_rulebook_is_explicit_and_matches_case_depth() -> None:
    rulebook = load_rulebook(ROOT / "design")
    case = load_case(ROOT / "cases" / "atlasbridge")
    assert rulebook.maximum_depth == case.maximum_depth == 4
    assert rulebook.rule_for("CALLS_INTERFACE") is not None
    assert rulebook.rule_for("CONTAINS") is None
    assert len(rulebook.digest) == 64


def test_attention_is_transparent() -> None:
    rulebook = load_rulebook(ROOT / "design")
    tier, reasons = attention_for(
        rulebook,
        entity_type="AUTHORITY_RULE",
        domain="AUTHORITY_AND_SEGREGATION",
        classification=ImpactClassification.DIRECT,
        origin_count=2,
        has_gap=False,
    )
    assert tier == AttentionTier.CRITICAL
    assert "DIRECT_CHANGE" in reasons
    assert "MULTI_CHANGE_COLLISION" in reasons


def test_explicit_unaffected_is_low_attention() -> None:
    rulebook = load_rulebook(ROOT / "design")
    tier, reasons = attention_for(
        rulebook,
        entity_type="NEGATIVE_CONTROL",
        domain="CONTROL_AND_POLICY",
        classification=ImpactClassification.EXPLICITLY_UNAFFECTED,
        origin_count=1,
        has_gap=False,
    )
    assert tier == AttentionTier.LOW
    assert reasons == ("EXPLICIT_NEGATIVE_CONTROL",)


def test_rulebook_rejects_invalid_depth(tmp_path: Path) -> None:
    for source in (ROOT / "design").glob("*.json"):
        (tmp_path / source.name).write_bytes(source.read_bytes())
    path = tmp_path / "propagation-rules.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["maximum_depth"] = 0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="maximum depth"):
        load_rulebook(tmp_path)
