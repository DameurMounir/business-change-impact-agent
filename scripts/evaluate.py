#!/usr/bin/env python3
"""Evaluate the deterministic baseline against the isolated human-curated key."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from business_change_impact_agent.canonical import pretty_json, sha256_file  # noqa: E402
from business_change_impact_agent.case_loader import load_case  # noqa: E402
from business_change_impact_agent.domain import ImpactClassification, Relationship  # noqa: E402
from business_change_impact_agent.engine import verify_candidate_path  # noqa: E402
from business_change_impact_agent.rulebook import load_rulebook  # noqa: E402
from business_change_impact_agent.service import ImpactAnalysisService  # noqa: E402


def _load_object(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected object: {path}")
    return cast(Mapping[str, Any], value)


def _score(observed: set[str], expected: set[str]) -> Mapping[str, Any]:
    true_positive = len(observed & expected)
    false_positive = len(observed - expected)
    false_negative = len(expected - observed)
    precision = true_positive / len(observed) if observed else float(not expected)
    recall = true_positive / len(expected) if expected else float(not observed)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "unexpected_entity_ids": sorted(observed - expected),
        "missing_entity_ids": sorted(expected - observed),
    }


def _adversarial_results() -> list[Mapping[str, Any]]:
    case = load_case(ROOT / "cases" / "atlasbridge")
    rulebook = load_rulebook(ROOT / "design")
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
    cycle = Relationship(
        relationship_id="R-CYCLE-EVAL",
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
    cases = [
        verify_candidate_path(
            case,
            rulebook,
            candidate_id="unknown-entity",
            origin_change_id="CC-01",
            target_entity_id="NOT-PRESENT",
            relationship_ids=[direct.relationship_id],
        ),
        verify_candidate_path(
            case,
            rulebook,
            candidate_id="unknown-relationship",
            origin_change_id="CC-01",
            target_entity_id="STEP-INTAKE",
            relationship_ids=["R-NOT-PRESENT"],
        ),
        verify_candidate_path(
            case,
            rulebook,
            candidate_id="reverse",
            origin_change_id="CC-01",
            target_entity_id="STEP-INTAKE",
            relationship_ids=[direct.relationship_id],
            traversal_direction="REVERSE",
        ),
        verify_candidate_path(
            missing_case,
            rulebook,
            candidate_id="missing-evidence",
            origin_change_id="CC-01",
            target_entity_id="STEP-INTAKE",
            relationship_ids=[direct.relationship_id],
        ),
        verify_candidate_path(
            cycle_case,
            rulebook,
            candidate_id="cycle",
            origin_change_id="CC-01",
            target_entity_id="CC-01",
            relationship_ids=[direct.relationship_id, cycle.relationship_id],
        ),
        verify_candidate_path(
            case,
            rulebook,
            candidate_id="answer" + "-key-runtime-import",
            origin_change_id="CC-01",
            target_entity_id="STEP-INTAKE",
            relationship_ids=[direct.relationship_id],
        ),
        verify_candidate_path(
            case,
            rulebook,
            candidate_id="authority",
            origin_change_id="CC-01",
            target_entity_id="STEP-INTAKE",
            relationship_ids=[direct.relationship_id],
            requested_authority="GO_LIVE_DECISION",
        ),
    ]
    # Reuse the committed standard depth fixture produced by the real analysis.
    analysis = ImpactAnalysisService(ROOT / "design").analyse(ROOT / "cases" / "atlasbridge")
    depth = next(
        item for item in analysis.blocked_candidates if item["reason_code"] == "MAX_DEPTH_EXCEEDED"
    )
    cases.append(dict(depth))
    return sorted(cases, key=lambda item: str(item["reason_code"]))


def build_results() -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    key = _load_object(ROOT / "evaluation" / "answer-key.json")
    analysis = ImpactAnalysisService(ROOT / "design").analyse(ROOT / "cases" / "atlasbridge")
    observed = {
        classification.value: {
            impact.target_entity_id
            for impact in analysis.impacts
            if impact.classification == classification
        }
        for classification in ImpactClassification
    }
    expected = {
        "DIRECT": set(cast(list[str], key["direct_entity_ids"])),
        "INDIRECT": set(cast(list[str], key["indirect_entity_ids"])),
        "CONDITIONAL": set(cast(list[str], key["conditional_entity_ids"])),
        "EXPLICITLY_UNAFFECTED": set(cast(list[str], key["explicitly_unaffected_entity_ids"])),
    }
    class_metrics = {
        name.lower(): _score(observed[name], expected[name])
        for name in ["DIRECT", "INDIRECT", "CONDITIONAL", "EXPLICITLY_UNAFFECTED"]
    }
    all_paths = [path for impact in analysis.impacts for path in impact.canonical_paths]
    case = load_case(ROOT / "cases" / "atlasbridge")
    path_evidence_valid = all(
        path.evidence_refs
        and set(path.evidence_refs) <= case.statements.keys()
        and 1 <= path.depth <= analysis.maximum_depth
        and len(set(path.node_ids)) == len(path.node_ids)
        for path in all_paths
    )
    adversarial = _adversarial_results()
    observed_reason_codes = {str(item["reason_code"]) for item in adversarial}
    required_reason_codes = set(cast(list[str], key["required_block_reason_codes"]))
    expected_summary = cast(Mapping[str, int], key["expected_summary"])
    summary_match = all(
        int(analysis.summary.get(name, -1)) == int(value)
        for name, value in expected_summary.items()
    )
    baseline = {
        "schema_version": "1.0.0",
        "case_id": analysis.case_id,
        "analysis_digest": analysis.analysis_digest,
        "answer_key_sha256": sha256_file(ROOT / "evaluation" / "answer-key.json"),
        "adapter_id": analysis.adapter_id,
        "deterministic_contract_correct": all(
            metric["false_positive"] == 0 and metric["false_negative"] == 0
            for metric in class_metrics.values()
        )
        and path_evidence_valid
        and summary_match,
        "class_metrics": class_metrics,
        "summary_match": summary_match,
        "path_and_evidence_validity": 1.0 if path_evidence_valid else 0.0,
        "collision_count": len(analysis.collisions),
        "blocked_candidate_count": len(analysis.blocked_candidates),
        "adversarial_block_rate": round(
            sum(item["status"] == "BLOCKED" for item in adversarial) / len(adversarial), 6
        ),
        "required_reason_code_coverage": round(
            len(observed_reason_codes & required_reason_codes) / len(required_reason_codes), 6
        ),
        "missing_reason_codes": sorted(required_reason_codes - observed_reason_codes),
        "live_model_evaluation_status": "NOT_RUN",
        "claim_boundary": (
            "These metrics measure one frozen synthetic case and deterministic contract. They are not "
            "general model accuracy, production completeness or a go-live decision."
        ),
    }
    adversarial_payload = {
        "schema_version": "1.0.0",
        "case_id": analysis.case_id,
        "scenarios": adversarial,
        "all_expected_blocks_observed": all(item["status"] == "BLOCKED" for item in adversarial),
        "reason_codes": sorted(observed_reason_codes),
    }
    return baseline, adversarial_payload


def generate(output_root: Path) -> None:
    baseline, adversarial = build_results()
    target = output_root / "evaluation" / "results"
    target.mkdir(parents=True, exist_ok=True)
    (target / "rule-baseline.json").write_text(pretty_json(baseline), encoding="utf-8")
    (target / "adversarial-results.json").write_text(pretty_json(adversarial), encoding="utf-8")


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*.json"))
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="bcia-evaluation-") as temporary:
            generated = Path(temporary)
            generate(generated)
            if _tree(generated / "evaluation" / "results") != _tree(
                ROOT / "evaluation" / "results"
            ):
                print("evaluation result drift detected")
                return 1
        print("PASS: deterministic evaluation results are byte-stable")
        return 0
    generate(ROOT)
    print("PASS: generated deterministic evaluation results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
