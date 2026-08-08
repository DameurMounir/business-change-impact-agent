"""Load an already validated synthetic case into typed objects."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from .canonical import canonical_json_bytes, sha256_bytes
from .case_validation import validate_case
from .domain import CaseModel, ChangeComponent, Entity, EvidenceStatement, Relationship
from .errors import ValidationError


def _read_object(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read validated case file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"expected JSON object in {path}")
    return cast(Mapping[str, Any], value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValidationError(f"{label} must be a string list")
    return tuple(value)


def load_case(case_dir: Path) -> CaseModel:
    """Validate and load a case without reading evaluator-only material."""

    validate_case(case_dir)
    case_dir = case_dir.resolve(strict=True)
    package = _read_object(case_dir / "change-package.json")
    metadata = _read_object(case_dir / "case-metadata.json")
    entity_payload = _read_object(case_dir / "entities.json")
    relationship_payload = _read_object(case_dir / "relationships.json")
    manifest = _read_object(case_dir / "manifest.json")

    statements: dict[str, EvidenceStatement] = {}
    for path in sorted((case_dir / "evidence").glob("*.json")):
        payload = _read_object(path)
        rows = payload.get("statements")
        if not isinstance(rows, list):
            raise ValidationError(f"statements missing from {path}")
        for raw in rows:
            if not isinstance(raw, dict):
                raise ValidationError(f"malformed statement in {path}")
            statement = EvidenceStatement(
                statement_id=str(raw["statement_id"]),
                document_id=str(raw["document_id"]),
                locator=str(raw["locator"]),
                text=str(raw["text"]),
                classification=str(raw["classification"]),
            )
            statements[statement.statement_id] = statement

    components: dict[str, ChangeComponent] = {}
    raw_components = package.get("components")
    if not isinstance(raw_components, list):
        raise ValidationError("components must be a list")
    for raw in raw_components:
        if not isinstance(raw, dict):
            raise ValidationError("malformed component")
        component = ChangeComponent(
            component_id=str(raw["component_id"]),
            title=str(raw["title"]),
            evidence_refs=_strings(raw["evidence_refs"], "component evidence_refs"),
            authorisation_status=str(raw["authorisation_status"]),
        )
        components[component.component_id] = component

    entities: dict[str, Entity] = {}
    raw_entities = entity_payload.get("entities")
    if not isinstance(raw_entities, list):
        raise ValidationError("entities must be a list")
    for raw in raw_entities:
        if not isinstance(raw, dict):
            raise ValidationError("malformed entity")
        owner = raw.get("owner_role_id")
        entity = Entity(
            entity_id=str(raw["entity_id"]),
            entity_type=str(raw["entity_type"]),
            name=str(raw["name"]),
            description=str(raw["description"]),
            primary_domain=str(raw["primary_domain"]),
            source_evidence_refs=_strings(raw["source_evidence_refs"], "entity evidence_refs"),
            applicability_status=str(raw["applicability_status"]),
            owner_role_id=str(owner) if owner is not None else None,
            tags=_strings(raw.get("tags", []), "entity tags"),
        )
        entities[entity.entity_id] = entity

    relationships: dict[str, Relationship] = {}
    raw_relationships = relationship_payload.get("relationships")
    if not isinstance(raw_relationships, list):
        raise ValidationError("relationships must be a list")
    for raw in raw_relationships:
        if not isinstance(raw, dict):
            raise ValidationError("malformed relationship")
        condition = raw.get("condition_id")
        gap = raw.get("evidence_gap_id")
        relationship = Relationship(
            relationship_id=str(raw["relationship_id"]),
            source_entity_id=str(raw["source_entity_id"]),
            target_entity_id=str(raw["target_entity_id"]),
            relationship_type=str(raw["relationship_type"]),
            direction=str(raw["direction"]),
            propagation_eligible=bool(raw["propagation_eligible"]),
            evidence_refs=_strings(raw["evidence_refs"], "relationship evidence_refs"),
            condition_id=str(condition) if condition is not None else None,
            evidence_gap_id=str(gap) if gap is not None else None,
        )
        relationships[relationship.relationship_id] = relationship

    digest_material = {
        "manifest": manifest,
        "case_id": package["case_id"],
        "maximum_depth": metadata["maximum_propagation_edges_from_change"],
    }
    return CaseModel(
        case_id=str(package["case_id"]),
        title=str(package["package_title"]),
        decision_question=str(package["decision_question"]),
        case_dir=case_dir,
        case_digest=sha256_bytes(canonical_json_bytes(digest_material)),
        maximum_depth=int(metadata["maximum_propagation_edges_from_change"]),
        components=components,
        entities=entities,
        relationships=relationships,
        statements=statements,
        explicitly_unaffected_entity_ids=_strings(
            package["explicitly_unaffected_entity_ids"], "explicitly unaffected IDs"
        ),
        forbidden_authorities=_strings(package["forbidden_authorities"], "forbidden authorities"),
    )
