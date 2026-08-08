"""Strict conversion between JSON mappings and typed analysis objects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from .domain import (
    AnalysisResult,
    AttentionTier,
    CollisionRecord,
    ImpactClassification,
    ImpactPath,
    ImpactRecord,
    Obligation,
    PathEdge,
)
from .errors import ValidationError


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be a list")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    rows = _sequence(value, label)
    if not all(isinstance(item, str) for item in rows):
        raise ValidationError(f"{label} must contain strings")
    return tuple(cast(Sequence[str], rows))


def analysis_from_dict(value: Mapping[str, Any]) -> AnalysisResult:
    """Parse an analysis mapping and reject malformed nested contracts."""

    impacts: list[ImpactRecord] = []
    for raw_impact in _sequence(value.get("impacts"), "impacts"):
        impact = _mapping(raw_impact, "impact")
        paths: list[ImpactPath] = []
        for raw_path in _sequence(impact.get("canonical_paths"), "canonical_paths"):
            path = _mapping(raw_path, "path")
            edges: list[PathEdge] = []
            for raw_edge in _sequence(path.get("edges"), "edges"):
                edge = _mapping(raw_edge, "edge")
                condition = edge.get("condition_id")
                gap = edge.get("evidence_gap_id")
                edges.append(
                    PathEdge(
                        relationship_id=str(edge["relationship_id"]),
                        source_entity_id=str(edge["source_entity_id"]),
                        target_entity_id=str(edge["target_entity_id"]),
                        relationship_type=str(edge["relationship_type"]),
                        evidence_refs=_strings(edge.get("evidence_refs"), "edge evidence_refs"),
                        condition_id=str(condition) if condition is not None else None,
                        evidence_gap_id=str(gap) if gap is not None else None,
                    )
                )
            paths.append(
                ImpactPath(
                    origin_change_id=str(path["origin_change_id"]),
                    target_entity_id=str(path["target_entity_id"]),
                    classification=ImpactClassification(str(path["classification"])),
                    edges=tuple(edges),
                    evidence_refs=_strings(path.get("evidence_refs"), "path evidence_refs"),
                    condition_ids=_strings(path.get("condition_ids"), "path condition_ids"),
                    evidence_gap_ids=_strings(
                        path.get("evidence_gap_ids"), "path evidence_gap_ids"
                    ),
                    path_digest=str(path["path_digest"]),
                )
            )
        obligations: list[Obligation] = []
        for raw_obligation in _sequence(impact.get("obligations"), "obligations"):
            obligation = _mapping(raw_obligation, "obligation")
            owner = obligation.get("owner_role_id")
            obligations.append(
                Obligation(
                    obligation_id=str(obligation["obligation_id"]),
                    obligation_type=str(obligation["obligation_type"]),
                    target_entity_id=str(obligation["target_entity_id"]),
                    description=str(obligation["description"]),
                    owner_role_id=str(owner) if owner is not None else None,
                    evidence_refs=_strings(
                        obligation.get("evidence_refs"), "obligation evidence_refs"
                    ),
                    status=str(obligation["status"]),
                )
            )
        impacts.append(
            ImpactRecord(
                target_entity_id=str(impact["target_entity_id"]),
                entity_name=str(impact["entity_name"]),
                entity_type=str(impact["entity_type"]),
                primary_domain=str(impact["primary_domain"]),
                classification=ImpactClassification(str(impact["classification"])),
                origin_change_ids=_strings(
                    impact.get("origin_change_ids"), "impact origin_change_ids"
                ),
                canonical_paths=tuple(paths),
                evidence_refs=_strings(impact.get("evidence_refs"), "impact evidence_refs"),
                condition_ids=_strings(impact.get("condition_ids"), "impact condition_ids"),
                evidence_gap_ids=_strings(
                    impact.get("evidence_gap_ids"), "impact evidence_gap_ids"
                ),
                attention_tier=AttentionTier(str(impact["attention_tier"])),
                reason_codes=_strings(impact.get("reason_codes"), "impact reason_codes"),
                obligations=tuple(obligations),
            )
        )

    collisions: list[CollisionRecord] = []
    for raw_collision in _sequence(value.get("collisions"), "collisions"):
        collision = _mapping(raw_collision, "collision")
        collisions.append(
            CollisionRecord(
                target_entity_id=str(collision["target_entity_id"]),
                origin_change_ids=_strings(
                    collision.get("origin_change_ids"), "collision origin_change_ids"
                ),
                classification=ImpactClassification(str(collision["classification"])),
                attention_tier=AttentionTier(str(collision["attention_tier"])),
            )
        )
    blocked = tuple(
        _mapping(item, "blocked candidate")
        for item in _sequence(value.get("blocked_candidates", []), "blocked_candidates")
    )
    raw_heatmap = _mapping(value.get("domain_heatmap", {}), "domain_heatmap")
    heatmap: dict[str, Mapping[str, int]] = {}
    for domain, raw_counts in raw_heatmap.items():
        counts = _mapping(raw_counts, f"domain heatmap {domain}")
        heatmap[str(domain)] = {str(key): int(number) for key, number in counts.items()}
    raw_summary = _mapping(value.get("summary"), "summary")
    return AnalysisResult(
        schema_version=str(value["schema_version"]),
        case_id=str(value["case_id"]),
        case_digest=str(value["case_digest"]),
        decision_question=str(value["decision_question"]),
        adapter_id=str(value["adapter_id"]),
        rulebook_digest=str(value["rulebook_digest"]),
        maximum_depth=int(value["maximum_depth"]),
        impacts=tuple(impacts),
        collisions=tuple(collisions),
        blocked_candidates=blocked,
        domain_heatmap=heatmap,
        summary={str(key): int(number) for key, number in raw_summary.items()},
        authority_statement=str(value["authority_statement"]),
        limitations=_strings(value.get("limitations"), "limitations"),
        analysis_digest=str(value["analysis_digest"]),
    )
