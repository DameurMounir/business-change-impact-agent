"""Typed domain contracts for business change impact analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class ImpactClassification(StrEnum):
    """Evidence status assigned to an assessed entity."""

    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"
    CONDITIONAL = "CONDITIONAL"
    EXPLICITLY_UNAFFECTED = "EXPLICITLY_UNAFFECTED"


class AttentionTier(StrEnum):
    """Transparent attention ordering; this is not model confidence."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ReviewAction(StrEnum):
    """Actions available to an authorised human reviewer."""

    CONFIRM = "CONFIRM"
    REQUEST_REVISION = "REQUEST_REVISION"
    EDIT = "EDIT"
    REJECT = "REJECT"


class ReviewState(StrEnum):
    """Persisted review lifecycle."""

    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    CONFIRMED = "CONFIRMED"
    CONFIRMED_WITH_EDITS = "CONFIRMED_WITH_EDITS"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class EvidenceStatement:
    statement_id: str
    document_id: str
    locator: str
    text: str
    classification: str


@dataclass(frozen=True)
class Entity:
    entity_id: str
    entity_type: str
    name: str
    description: str
    primary_domain: str
    source_evidence_refs: tuple[str, ...]
    applicability_status: str
    owner_role_id: str | None
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Relationship:
    relationship_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    direction: str
    propagation_eligible: bool
    evidence_refs: tuple[str, ...]
    condition_id: str | None
    evidence_gap_id: str | None


@dataclass(frozen=True)
class ChangeComponent:
    component_id: str
    title: str
    evidence_refs: tuple[str, ...]
    authorisation_status: str


@dataclass(frozen=True)
class CaseModel:
    case_id: str
    title: str
    decision_question: str
    case_dir: Path
    case_digest: str
    maximum_depth: int
    components: Mapping[str, ChangeComponent]
    entities: Mapping[str, Entity]
    relationships: Mapping[str, Relationship]
    statements: Mapping[str, EvidenceStatement]
    explicitly_unaffected_entity_ids: tuple[str, ...]
    forbidden_authorities: tuple[str, ...]


@dataclass(frozen=True)
class PathEdge:
    relationship_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    evidence_refs: tuple[str, ...]
    condition_id: str | None
    evidence_gap_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "relationship_id": self.relationship_id,
            "source_entity_id": self.source_entity_id,
            "target_entity_id": self.target_entity_id,
            "relationship_type": self.relationship_type,
            "evidence_refs": list(self.evidence_refs),
            "condition_id": self.condition_id,
            "evidence_gap_id": self.evidence_gap_id,
        }


@dataclass(frozen=True)
class ImpactPath:
    origin_change_id: str
    target_entity_id: str
    classification: ImpactClassification
    edges: tuple[PathEdge, ...]
    evidence_refs: tuple[str, ...]
    condition_ids: tuple[str, ...]
    evidence_gap_ids: tuple[str, ...]
    path_digest: str

    @property
    def depth(self) -> int:
        return len(self.edges)

    @property
    def node_ids(self) -> tuple[str, ...]:
        if not self.edges:
            return (self.origin_change_id,)
        return (
            self.edges[0].source_entity_id,
            *tuple(edge.target_entity_id for edge in self.edges),
        )

    @property
    def relationship_ids(self) -> tuple[str, ...]:
        return tuple(edge.relationship_id for edge in self.edges)

    def as_dict(self) -> dict[str, Any]:
        return {
            "origin_change_id": self.origin_change_id,
            "target_entity_id": self.target_entity_id,
            "classification": self.classification.value,
            "depth": self.depth,
            "node_ids": list(self.node_ids),
            "relationship_ids": list(self.relationship_ids),
            "edges": [edge.as_dict() for edge in self.edges],
            "evidence_refs": list(self.evidence_refs),
            "condition_ids": list(self.condition_ids),
            "evidence_gap_ids": list(self.evidence_gap_ids),
            "path_digest": self.path_digest,
            "canonical": True,
        }


@dataclass(frozen=True)
class Obligation:
    obligation_id: str
    obligation_type: str
    target_entity_id: str
    description: str
    owner_role_id: str | None
    evidence_refs: tuple[str, ...]
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "obligation_type": self.obligation_type,
            "target_entity_id": self.target_entity_id,
            "description": self.description,
            "owner_role_id": self.owner_role_id,
            "evidence_refs": list(self.evidence_refs),
            "status": self.status,
        }


@dataclass(frozen=True)
class ImpactRecord:
    target_entity_id: str
    entity_name: str
    entity_type: str
    primary_domain: str
    classification: ImpactClassification
    origin_change_ids: tuple[str, ...]
    canonical_paths: tuple[ImpactPath, ...]
    evidence_refs: tuple[str, ...]
    condition_ids: tuple[str, ...]
    evidence_gap_ids: tuple[str, ...]
    attention_tier: AttentionTier
    reason_codes: tuple[str, ...]
    obligations: tuple[Obligation, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_entity_id": self.target_entity_id,
            "entity_name": self.entity_name,
            "entity_type": self.entity_type,
            "primary_domain": self.primary_domain,
            "classification": self.classification.value,
            "origin_change_ids": list(self.origin_change_ids),
            "canonical_paths": [path.as_dict() for path in self.canonical_paths],
            "evidence_refs": list(self.evidence_refs),
            "condition_ids": list(self.condition_ids),
            "evidence_gap_ids": list(self.evidence_gap_ids),
            "attention_tier": self.attention_tier.value,
            "reason_codes": list(self.reason_codes),
            "obligations": [item.as_dict() for item in self.obligations],
        }


@dataclass(frozen=True)
class CollisionRecord:
    target_entity_id: str
    origin_change_ids: tuple[str, ...]
    classification: ImpactClassification
    attention_tier: AttentionTier

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_entity_id": self.target_entity_id,
            "origin_change_ids": list(self.origin_change_ids),
            "classification": self.classification.value,
            "attention_tier": self.attention_tier.value,
        }


@dataclass(frozen=True)
class AnalysisResult:
    schema_version: str
    case_id: str
    case_digest: str
    decision_question: str
    adapter_id: str
    rulebook_digest: str
    maximum_depth: int
    impacts: tuple[ImpactRecord, ...]
    collisions: tuple[CollisionRecord, ...]
    blocked_candidates: tuple[Mapping[str, Any], ...]
    domain_heatmap: Mapping[str, Mapping[str, int]]
    summary: Mapping[str, int]
    authority_statement: str
    limitations: tuple[str, ...]
    analysis_digest: str

    def as_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "case_digest": self.case_digest,
            "decision_question": self.decision_question,
            "adapter_id": self.adapter_id,
            "rulebook_digest": self.rulebook_digest,
            "maximum_depth": self.maximum_depth,
            "impacts": [impact.as_dict() for impact in self.impacts],
            "collisions": [collision.as_dict() for collision in self.collisions],
            "blocked_candidates": [dict(item) for item in self.blocked_candidates],
            "domain_heatmap": {
                domain: dict(sorted(counts.items()))
                for domain, counts in sorted(self.domain_heatmap.items())
            },
            "summary": dict(sorted(self.summary.items())),
            "authority_statement": self.authority_statement,
            "limitations": list(self.limitations),
        }
        if include_digest:
            result["analysis_digest"] = self.analysis_digest
        return result
