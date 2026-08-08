"""Deterministic evidence-bound graph traversal engine."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import replace
from typing import Any, Iterable, Mapping, Sequence

from .canonical import canonical_json_bytes, sha256_bytes
from .case_validation import DIRECT_RELATION_TYPES
from .domain import (
    AnalysisResult,
    AttentionTier,
    CaseModel,
    CollisionRecord,
    ImpactClassification,
    ImpactPath,
    ImpactRecord,
    Obligation,
    PathEdge,
    Relationship,
)
from .errors import ValidationError
from .rulebook import Rulebook, attention_for

SCHEMA_VERSION = "1.0.0"
_AUTHORITY_STATEMENT = (
    "This assessment identifies evidence-linked direct, indirect, conditional and explicitly "
    "unaffected entities. It does not approve implementation, spending, staffing, vendor selection, "
    "risk acceptance or go-live."
)
_LIMITATIONS = (
    "The result is limited to the frozen synthetic AtlasBridge case and its committed rulebook.",
    "Absence from the graph is not proof that an entity is unaffected in a real organisation.",
    "Conditional impacts remain unresolved until their stated assumptions and evidence gaps are closed.",
    "Attention tiers are transparent rules, not model confidence or risk acceptance.",
    "No production system, external service or business record is modified.",
)


def _edge(relationship: Relationship) -> PathEdge:
    return PathEdge(
        relationship_id=relationship.relationship_id,
        source_entity_id=relationship.source_entity_id,
        target_entity_id=relationship.target_entity_id,
        relationship_type=relationship.relationship_type,
        evidence_refs=relationship.evidence_refs,
        condition_id=relationship.condition_id,
        evidence_gap_id=relationship.evidence_gap_id,
    )


def _path(
    origin_change_id: str,
    edges: Sequence[PathEdge],
    classification: ImpactClassification,
) -> ImpactPath:
    evidence = tuple(sorted({item for edge in edges for item in edge.evidence_refs}))
    conditions = tuple(sorted({edge.condition_id for edge in edges if edge.condition_id is not None}))
    gaps = tuple(sorted({edge.evidence_gap_id for edge in edges if edge.evidence_gap_id is not None}))
    material = {
        "origin_change_id": origin_change_id,
        "classification": classification.value,
        "relationship_ids": [edge.relationship_id for edge in edges],
        "evidence_refs": list(evidence),
        "condition_ids": list(conditions),
        "evidence_gap_ids": list(gaps),
    }
    return ImpactPath(
        origin_change_id=origin_change_id,
        target_entity_id=edges[-1].target_entity_id,
        classification=classification,
        edges=tuple(edges),
        evidence_refs=evidence,
        condition_ids=conditions,
        evidence_gap_ids=gaps,
        path_digest=sha256_bytes(canonical_json_bytes(material)),
    )


def _path_key(path: ImpactPath) -> tuple[int, int, tuple[str, ...], tuple[str, ...]]:
    conditional_rank = 1 if path.classification == ImpactClassification.CONDITIONAL else 0
    return conditional_rank, path.depth, path.relationship_ids, path.node_ids


def _classification(paths: Iterable[ImpactPath]) -> ImpactClassification:
    values = {path.classification for path in paths}
    if ImpactClassification.DIRECT in values:
        return ImpactClassification.DIRECT
    if ImpactClassification.INDIRECT in values:
        return ImpactClassification.INDIRECT
    return ImpactClassification.CONDITIONAL


def _obligations(
    rulebook: Rulebook,
    *,
    target_entity_id: str,
    entity_type: str,
    entity_name: str,
    owner_role_id: str | None,
    evidence_refs: tuple[str, ...],
    evidence_gap_ids: tuple[str, ...],
) -> tuple[Obligation, ...]:
    template = rulebook.obligation_templates.get(
        entity_type, rulebook.obligation_templates["default"]
    )
    items = [
        Obligation(
            obligation_id="OBL-" + sha256_bytes(
                canonical_json_bytes(
                    {
                        "target": target_entity_id,
                        "type": template["obligation_type"],
                    }
                )
            )[:16].upper(),
            obligation_type=template["obligation_type"],
            target_entity_id=target_entity_id,
            description=template["description"].replace("{entity_name}", entity_name),
            owner_role_id=owner_role_id,
            evidence_refs=evidence_refs,
            status="PROPOSED_FOR_HUMAN_REVIEW",
        )
    ]
    if evidence_gap_ids and template["obligation_type"] != "CLOSE_EVIDENCE_GAP":
        items.append(
            Obligation(
                obligation_id="OBL-" + sha256_bytes(
                    canonical_json_bytes(
                        {
                            "target": target_entity_id,
                            "type": "CLOSE_EVIDENCE_GAP",
                            "gaps": list(evidence_gap_ids),
                        }
                    )
                )[:16].upper(),
                obligation_type="CLOSE_EVIDENCE_GAP",
                target_entity_id=target_entity_id,
                description=(
                    "Close and retain evidence for the stated gap(s) before treating this conditional "
                    "impact as confirmed: " + ", ".join(evidence_gap_ids)
                ),
                owner_role_id=owner_role_id,
                evidence_refs=evidence_refs,
                status="PROPOSED_FOR_HUMAN_REVIEW",
            )
        )
    return tuple(items)


def _find_relationship(
    relationships: Mapping[str, Relationship],
    source: str,
    target: str,
) -> str:
    matches = sorted(
        relationship.relationship_id
        for relationship in relationships.values()
        if relationship.source_entity_id == source and relationship.target_entity_id == target
    )
    if not matches:
        raise ValidationError(f"relationship not found for standard candidate: {source} -> {target}")
    return matches[0]


def verify_candidate_path(
    case: CaseModel,
    rulebook: Rulebook,
    *,
    candidate_id: str,
    origin_change_id: str,
    target_entity_id: str,
    relationship_ids: Sequence[str],
    traversal_direction: str = "FORWARD",
    requested_authority: str = "IMPACT_ASSESSMENT_ONLY",
) -> dict[str, Any]:
    """Verify one proposed impact path and return a fail-closed verdict."""

    def blocked(reason: str, detail: str) -> dict[str, Any]:
        return {
            "candidate_id": candidate_id,
            "status": "BLOCKED",
            "reason_code": reason,
            "detail": detail,
            "origin_change_id": origin_change_id,
            "target_entity_id": target_entity_id,
            "relationship_ids": list(relationship_ids),
        }

    identifiers = [candidate_id, origin_change_id, target_entity_id, *relationship_ids]
    forbidden_markers = ("answer" + "-key", "answer" + "_" + "key")
    if any(marker in value.lower() for value in identifiers for marker in forbidden_markers):
        return blocked("ANSWER_KEY_IDENTIFIER", "evaluator-only identifier is forbidden at runtime")
    if requested_authority != "IMPACT_ASSESSMENT_ONLY":
        return blocked("AUTHORITY_ESCALATION", f"requested authority is forbidden: {requested_authority}")
    if traversal_direction != "FORWARD":
        return blocked("FORBIDDEN_DIRECTION", "reverse traversal requires an explicit rule and none exists")
    if origin_change_id not in case.components or origin_change_id not in case.entities:
        return blocked("UNKNOWN_ENTITY", f"unknown change component: {origin_change_id}")
    if target_entity_id not in case.entities:
        return blocked("UNKNOWN_ENTITY", f"unknown target entity: {target_entity_id}")
    if not relationship_ids:
        return blocked("UNKNOWN_RELATIONSHIP", "candidate path is empty")
    if len(relationship_ids) > min(case.maximum_depth, rulebook.maximum_depth):
        return blocked("MAX_DEPTH_EXCEEDED", "candidate path exceeds the published depth boundary")

    current = origin_change_id
    visited = {current}
    for index, relationship_id in enumerate(relationship_ids):
        relationship = case.relationships.get(relationship_id)
        if relationship is None:
            return blocked("UNKNOWN_RELATIONSHIP", f"unknown relationship: {relationship_id}")
        if relationship.direction != "FORWARD" or relationship.source_entity_id != current:
            return blocked("FORBIDDEN_DIRECTION", f"relationship does not continue forward: {relationship_id}")
        if not relationship.evidence_refs or any(
            evidence_ref not in case.statements for evidence_ref in relationship.evidence_refs
        ):
            return blocked("MISSING_EVIDENCE", f"relationship evidence is invalid: {relationship_id}")
        if index == 0:
            if relationship.relationship_type not in DIRECT_RELATION_TYPES:
                return blocked("UNKNOWN_RELATIONSHIP", "first edge is not an authorised direct change")
        else:
            rule = rulebook.rule_for(relationship.relationship_type)
            if rule is None or not relationship.propagation_eligible:
                return blocked(
                    "UNKNOWN_RELATIONSHIP",
                    f"relationship is not propagation-authorised: {relationship_id}",
                )
        current = relationship.target_entity_id
        if current in visited:
            return blocked("CYCLE_DETECTED", f"cycle detected at {current}")
        visited.add(current)
    if current != target_entity_id:
        return blocked("UNKNOWN_ENTITY", f"path terminates at {current}, not {target_entity_id}")
    return {
        "candidate_id": candidate_id,
        "status": "SUPPORTED",
        "reason_code": "EVIDENCE_PATH_VERIFIED",
        "detail": "candidate path satisfies direction, evidence, rule and depth controls",
        "origin_change_id": origin_change_id,
        "target_entity_id": target_entity_id,
        "relationship_ids": list(relationship_ids),
    }


def _standard_blocked_candidates(case: CaseModel, rulebook: Rulebook) -> tuple[Mapping[str, Any], ...]:
    workflow_path = [
        _find_relationship(case.relationships, "CC-03", "SYS-WORKFLOW"),
        _find_relationship(case.relationships, "SYS-WORKFLOW", "IFACE-SCREENING"),
        _find_relationship(case.relationships, "IFACE-SCREENING", "INT-SCREENING"),
        _find_relationship(case.relationships, "INT-SCREENING", "EXT-SCREENING"),
        _find_relationship(case.relationships, "EXT-SCREENING", "VENDOR-CHECKRIGHT"),
    ]
    candidates = [
        verify_candidate_path(
            case,
            rulebook,
            candidate_id="CAND-UNKNOWN-TARGET",
            origin_change_id="CC-06",
            target_entity_id="VENDOR-NOT-IN-GRAPH",
            relationship_ids=["R-NOT-PRESENT"],
        ),
        verify_candidate_path(
            case,
            rulebook,
            candidate_id="CAND-REVERSE",
            origin_change_id="CC-03",
            target_entity_id="STEP-RISK-REVIEW",
            relationship_ids=[workflow_path[0]],
            traversal_direction="REVERSE",
        ),
        verify_candidate_path(
            case,
            rulebook,
            candidate_id="CAND-DEPTH-FIVE",
            origin_change_id="CC-03",
            target_entity_id="VENDOR-CHECKRIGHT",
            relationship_ids=workflow_path,
        ),
        verify_candidate_path(
            case,
            rulebook,
            candidate_id="answer" + "-key-import",
            origin_change_id="CC-03",
            target_entity_id="SYS-WORKFLOW",
            relationship_ids=[workflow_path[0]],
        ),
        verify_candidate_path(
            case,
            rulebook,
            candidate_id="CAND-GO-LIVE",
            origin_change_id="CC-03",
            target_entity_id="SYS-WORKFLOW",
            relationship_ids=[workflow_path[0]],
            requested_authority="GO_LIVE_DECISION",
        ),
    ]
    return tuple(candidate for candidate in candidates if candidate["status"] == "BLOCKED")


def analyse_case(
    case: CaseModel,
    rulebook: Rulebook,
    *,
    adapter_id: str = "deterministic-rule-v1",
) -> AnalysisResult:
    """Trace direct and eligible indirect impacts with canonical paths."""

    if case.maximum_depth != rulebook.maximum_depth:
        raise ValidationError("case and rulebook maximum depth disagree")
    outgoing: dict[str, list[Relationship]] = defaultdict(list)
    for relationship in case.relationships.values():
        outgoing[relationship.source_entity_id].append(relationship)
    for rows in outgoing.values():
        rows.sort(key=lambda item: item.relationship_id)

    best: dict[tuple[str, str], ImpactPath] = {}
    for component_id in sorted(case.components):
        queue: deque[ImpactPath] = deque()
        for relationship in outgoing.get(component_id, []):
            if relationship.relationship_type not in DIRECT_RELATION_TYPES:
                continue
            direct_path = _path(component_id, [_edge(relationship)], ImpactClassification.DIRECT)
            key = (component_id, relationship.target_entity_id)
            current = best.get(key)
            if current is None or _path_key(direct_path) < _path_key(current):
                best[key] = direct_path
            queue.append(direct_path)

        while queue:
            current_path = queue.popleft()
            if current_path.depth >= rulebook.maximum_depth:
                continue
            current_entity = current_path.target_entity_id
            visited = set(current_path.node_ids)
            for relationship in outgoing.get(current_entity, []):
                rule = rulebook.rule_for(relationship.relationship_type)
                depth = current_path.depth + 1
                if (
                    rule is None
                    or not relationship.propagation_eligible
                    or relationship.direction != "FORWARD"
                    or depth < rule.minimum_depth
                    or depth > rule.maximum_depth
                    or relationship.target_entity_id in visited
                    or relationship.target_entity_id in case.components
                ):
                    continue
                edges = current_path.edges + (_edge(relationship),)
                conditional = any(
                    edge.condition_id is not None or edge.evidence_gap_id is not None for edge in edges
                )
                classification = (
                    ImpactClassification.CONDITIONAL
                    if conditional
                    else ImpactClassification.INDIRECT
                )
                candidate = _path(component_id, edges, classification)
                key = (component_id, candidate.target_entity_id)
                existing = best.get(key)
                if existing is None or _path_key(candidate) < _path_key(existing):
                    best[key] = candidate
                    queue.append(candidate)

    paths_by_target: dict[str, list[ImpactPath]] = defaultdict(list)
    for path in best.values():
        paths_by_target[path.target_entity_id].append(path)

    records: list[ImpactRecord] = []
    for target_id, paths in sorted(paths_by_target.items()):
        entity = case.entities[target_id]
        paths.sort(key=lambda item: (item.origin_change_id, _path_key(item)))
        classification = _classification(paths)
        origins = tuple(sorted({path.origin_change_id for path in paths}))
        evidence = tuple(
            sorted(
                set(entity.source_evidence_refs)
                | {reference for path in paths for reference in path.evidence_refs}
            )
        )
        conditions = tuple(sorted({value for path in paths for value in path.condition_ids}))
        gaps = tuple(sorted({value for path in paths for value in path.evidence_gap_ids}))
        tier, reasons = attention_for(
            rulebook,
            entity_type=entity.entity_type,
            domain=entity.primary_domain,
            classification=classification,
            origin_count=len(origins),
            has_gap=bool(gaps),
        )
        propagation_reasons = {
            rule.reason_code
            for path in paths
            for edge in path.edges[1:]
            if (rule := rulebook.rule_for(edge.relationship_type)) is not None
        }
        records.append(
            ImpactRecord(
                target_entity_id=target_id,
                entity_name=entity.name,
                entity_type=entity.entity_type,
                primary_domain=entity.primary_domain,
                classification=classification,
                origin_change_ids=origins,
                canonical_paths=tuple(paths),
                evidence_refs=evidence,
                condition_ids=conditions,
                evidence_gap_ids=gaps,
                attention_tier=tier,
                reason_codes=tuple(sorted(set(reasons) | propagation_reasons)),
                obligations=_obligations(
                    rulebook,
                    target_entity_id=target_id,
                    entity_type=entity.entity_type,
                    entity_name=entity.name,
                    owner_role_id=entity.owner_role_id,
                    evidence_refs=evidence,
                    evidence_gap_ids=gaps,
                ),
            )
        )

    exclude_relationships = {
        relationship.target_entity_id: relationship
        for relationship in case.relationships.values()
        if relationship.relationship_type == "EXPLICITLY_EXCLUDES"
        and relationship.source_entity_id in case.components
    }
    for target_id in case.explicitly_unaffected_entity_ids:
        entity = case.entities[target_id]
        relationship = exclude_relationships[target_id]
        path = _path(
            relationship.source_entity_id,
            [_edge(relationship)],
            ImpactClassification.EXPLICITLY_UNAFFECTED,
        )
        tier, reasons = attention_for(
            rulebook,
            entity_type=entity.entity_type,
            domain=entity.primary_domain,
            classification=ImpactClassification.EXPLICITLY_UNAFFECTED,
            origin_count=1,
            has_gap=False,
        )
        records.append(
            ImpactRecord(
                target_entity_id=target_id,
                entity_name=entity.name,
                entity_type=entity.entity_type,
                primary_domain=entity.primary_domain,
                classification=ImpactClassification.EXPLICITLY_UNAFFECTED,
                origin_change_ids=(relationship.source_entity_id,),
                canonical_paths=(path,),
                evidence_refs=tuple(sorted(set(entity.source_evidence_refs) | set(path.evidence_refs))),
                condition_ids=(),
                evidence_gap_ids=(),
                attention_tier=tier,
                reason_codes=reasons,
                obligations=(),
            )
        )

    classification_order = {
        ImpactClassification.DIRECT: 0,
        ImpactClassification.INDIRECT: 1,
        ImpactClassification.CONDITIONAL: 2,
        ImpactClassification.EXPLICITLY_UNAFFECTED: 3,
    }
    records.sort(key=lambda item: (classification_order[item.classification], item.target_entity_id))
    collisions = tuple(
        CollisionRecord(
            target_entity_id=record.target_entity_id,
            origin_change_ids=record.origin_change_ids,
            classification=record.classification,
            attention_tier=(
                record.attention_tier
                if record.attention_tier == AttentionTier.CRITICAL
                else AttentionTier.HIGH
            ),
        )
        for record in records
        if len(record.origin_change_ids) > 1
        and record.classification != ImpactClassification.EXPLICITLY_UNAFFECTED
    )

    heatmap: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    summary: dict[str, int] = defaultdict(int)
    obligation_ids: set[str] = set()
    for record in records:
        heatmap[record.primary_domain][record.classification.value] += 1
        summary[record.classification.value.lower()] += 1
        for obligation in record.obligations:
            obligation_ids.add(obligation.obligation_id)
    summary["collisions"] = len(collisions)
    summary["obligations"] = len(obligation_ids)
    blocked_candidates = _standard_blocked_candidates(case, rulebook)
    summary["blocked_candidates"] = len(blocked_candidates)

    provisional = AnalysisResult(
        schema_version=SCHEMA_VERSION,
        case_id=case.case_id,
        case_digest=case.case_digest,
        decision_question=case.decision_question,
        adapter_id=adapter_id,
        rulebook_digest=rulebook.digest,
        maximum_depth=rulebook.maximum_depth,
        impacts=tuple(records),
        collisions=collisions,
        blocked_candidates=blocked_candidates,
        domain_heatmap=heatmap,
        summary=summary,
        authority_statement=_AUTHORITY_STATEMENT,
        limitations=_LIMITATIONS,
        analysis_digest="",
    )
    digest = sha256_bytes(canonical_json_bytes(provisional.as_dict(include_digest=False)))
    return replace(provisional, analysis_digest=digest)
