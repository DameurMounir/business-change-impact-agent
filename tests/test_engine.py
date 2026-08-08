from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from business_change_impact_agent.adapters import FixtureAdapter
from business_change_impact_agent.case_loader import load_case
from business_change_impact_agent.domain import ImpactClassification, Relationship
from business_change_impact_agent.engine import verify_candidate_path
from business_change_impact_agent.errors import ValidationError
from business_change_impact_agent.rulebook import load_rulebook
from business_change_impact_agent.service import ImpactAnalysisService

ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "cases" / "atlasbridge"
DESIGN_DIR = ROOT / "design"


def result():
    return ImpactAnalysisService(DESIGN_DIR).analyse(CASE_DIR)


def test_analysis_is_deterministic_and_digest_bound() -> None:
    first = result()
    second = result()
    assert first.as_dict() == second.as_dict()
    assert len(first.analysis_digest) == 64
    assert first.summary == {
        "blocked_candidates": 5,
        "collisions": 22,
        "conditional": 3,
        "direct": 36,
        "explicitly_unaffected": 6,
        "indirect": 12,
        "obligations": 53,
    }


def test_direct_indirect_conditional_and_unaffected_are_separate() -> None:
    impacts = {item.target_entity_id: item for item in result().impacts}
    assert impacts["STEP-RISK-REVIEW"].classification == ImpactClassification.DIRECT
    assert impacts["IFACE-SCREENING"].classification == ImpactClassification.INDIRECT
    assert impacts["EXT-SCREENING"].classification == ImpactClassification.CONDITIONAL
    assert impacts["NEG-PAYROLL"].classification == ImpactClassification.EXPLICITLY_UNAFFECTED
    assert impacts["EXT-SCREENING"].evidence_gap_ids == ("GAP-VENDOR-CAPACITY",)
    assert impacts["NEG-PAYROLL"].obligations == ()


def test_external_service_path_is_four_edges_and_vendor_is_blocked() -> None:
    analysis = result()
    external = next(item for item in analysis.impacts if item.target_entity_id == "EXT-SCREENING")
    path = next(item for item in external.canonical_paths if item.origin_change_id == "CC-03")
    assert path.depth == 4
    assert path.node_ids == (
        "CC-03",
        "SYS-WORKFLOW",
        "IFACE-SCREENING",
        "INT-SCREENING",
        "EXT-SCREENING",
    )
    depth_block = next(
        item for item in analysis.blocked_candidates if item["candidate_id"] == "CAND-DEPTH-FIVE"
    )
    assert depth_block["reason_code"] == "MAX_DEPTH_EXCEEDED"
    assert not any(item.target_entity_id == "VENDOR-CHECKRIGHT" for item in analysis.impacts)


def test_every_path_is_forward_evidenced_and_within_depth() -> None:
    analysis = result()
    case = load_case(CASE_DIR)
    for impact in analysis.impacts:
        for path in impact.canonical_paths:
            assert 1 <= path.depth <= 4
            assert len(path.node_ids) == path.depth + 1
            assert len(set(path.node_ids)) == len(path.node_ids)
            for edge in path.edges:
                assert edge.evidence_refs
                assert set(edge.evidence_refs) <= case.statements.keys()


def test_collisions_are_not_duplicate_counts() -> None:
    analysis = result()
    collision = next(
        item for item in analysis.collisions if item.target_entity_id == "DATA-CASE-STATUS"
    )
    assert set(collision.origin_change_ids) >= {"CC-02", "CC-04", "CC-06"}
    assert sum(1 for item in analysis.impacts if item.target_entity_id == "DATA-CASE-STATUS") == 1


def test_standard_blocked_reason_codes() -> None:
    codes = {str(item["reason_code"]) for item in result().blocked_candidates}
    assert codes == {
        "UNKNOWN_ENTITY",
        "FORBIDDEN_DIRECTION",
        "MAX_DEPTH_EXCEEDED",
        "ANSWER_KEY_IDENTIFIER",
        "AUTHORITY_ESCALATION",
    }


def test_candidate_rejects_missing_evidence_and_cycle() -> None:
    case = load_case(CASE_DIR)
    rulebook = load_rulebook(DESIGN_DIR)
    direct = next(
        relationship
        for relationship in case.relationships.values()
        if relationship.source_entity_id == "CC-01"
        and relationship.target_entity_id == "STEP-INTAKE"
    )
    missing = replace(direct, evidence_refs=())
    missing_case = replace(
        case, relationships={**case.relationships, direct.relationship_id: missing}
    )
    verdict = verify_candidate_path(
        missing_case,
        rulebook,
        candidate_id="missing-evidence",
        origin_change_id="CC-01",
        target_entity_id="STEP-INTAKE",
        relationship_ids=[direct.relationship_id],
    )
    assert verdict["reason_code"] == "MISSING_EVIDENCE"

    cycle = Relationship(
        relationship_id="R-CYCLE",
        source_entity_id="STEP-INTAKE",
        target_entity_id="CC-01",
        relationship_type="USES_SYSTEM",
        direction="FORWARD",
        propagation_eligible=True,
        evidence_refs=("S-001",),
        condition_id=None,
        evidence_gap_id=None,
    )
    cycle_case = replace(case, relationships={**case.relationships, cycle.relationship_id: cycle})
    verdict = verify_candidate_path(
        cycle_case,
        rulebook,
        candidate_id="cycle",
        origin_change_id="CC-01",
        target_entity_id="CC-01",
        relationship_ids=[direct.relationship_id, cycle.relationship_id],
    )
    assert verdict["reason_code"] == "CYCLE_DETECTED"


def test_fixture_adapter_is_verified_fail_closed() -> None:
    baseline = result()
    valid = ImpactAnalysisService(DESIGN_DIR, FixtureAdapter(baseline)).analyse(CASE_DIR)
    assert valid.adapter_id == "fixture-v1"
    tampered = replace(baseline, summary={**baseline.summary, "direct": 999})
    with pytest.raises(ValidationError, match="differs"):
        ImpactAnalysisService(DESIGN_DIR, FixtureAdapter(tampered)).analyse(CASE_DIR)


def test_prompt_like_evidence_does_not_change_control_flow() -> None:
    analysis = result()
    assert analysis.summary["direct"] == 36
    assert not any(item.target_entity_id == "VENDOR-NOT-IN-GRAPH" for item in analysis.impacts)
