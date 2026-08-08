"""Validation for the frozen AtlasBridge case."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import sha256_file
from .errors import SecurityBoundaryError, ValidationError

SCHEMA_VERSION = "1.0.0"
MAX_JSON_BYTES = 2_000_000

ENTITY_TYPES = {
    "CHANGE_COMPONENT",
    "BUSINESS_CAPABILITY",
    "PROCESS",
    "PROCESS_STEP",
    "PROCEDURE",
    "ROLE",
    "TEAM",
    "AUTHORITY_RULE",
    "SEGREGATION_RULE",
    "TRAINING_ITEM",
    "SYSTEM",
    "APPLICATION_COMPONENT",
    "INTERFACE",
    "INTEGRATION",
    "DATA_OBJECT",
    "DATA_OWNER",
    "REPORT",
    "KPI",
    "SLA",
    "CONTROL",
    "POLICY",
    "CUSTOMER_TOUCHPOINT",
    "COMMUNICATION_TEMPLATE",
    "ACCESSIBILITY_REQUIREMENT",
    "EXTERNAL_SERVICE",
    "VENDOR",
    "TEST_CASE",
    "RUNBOOK",
    "SUPPORT_PROCEDURE",
    "ASSUMPTION",
    "CONSTRAINT",
    "EVIDENCE_GAP",
    "NEGATIVE_CONTROL",
}

DIRECT_RELATION_TYPES = {
    "INTRODUCES",
    "MODIFIES",
    "REMOVES",
    "REPLACES",
    "RESEQUENCES",
    "AUTOMATES",
    "TRANSFERS_OWNERSHIP",
    "ADDS_CONTROL",
    "CHANGES_THRESHOLD",
    "CHANGES_INTERFACE",
}

RELATION_TYPES = DIRECT_RELATION_TYPES | {
    "CONTAINS",
    "PART_OF",
    "PRECEDES",
    "FOLLOWS",
    "PERFORMED_BY",
    "ACCOUNTABLE_TO",
    "OWNED_BY",
    "REQUIRES_AUTHORITY",
    "SEGREGATED_FROM",
    "REQUIRES_TRAINING",
    "USES_SYSTEM",
    "IMPLEMENTED_BY",
    "CALLS_INTERFACE",
    "INTEGRATES_WITH",
    "DEPENDS_ON_SERVICE",
    "SUPPLIED_BY",
    "READS_DATA",
    "WRITES_DATA",
    "OWNS_DATA",
    "REPORTED_IN",
    "MEASURED_BY",
    "GOVERNED_BY_CONTROL",
    "GOVERNED_BY_POLICY",
    "TESTED_BY",
    "NOTIFIES_THROUGH",
    "SUBJECT_TO_ACCESSIBILITY",
    "OPERATED_BY",
    "SUPPORTED_BY",
    "DOCUMENTED_IN_RUNBOOK",
    "ESCALATES_TO",
    "TRIGGERS",
    "MONITORS",
    "HAS_SERVICE_TARGET",
    "CONDITIONED_BY",
    "EXPLICITLY_EXCLUDES",
}

DOMAIN_CODES = {
    "BUSINESS_CAPABILITY",
    "END_TO_END_PROCESS",
    "PROCESS_STEP",
    "OPERATING_PROCEDURE",
    "ROLE_AND_TEAM",
    "AUTHORITY_AND_SEGREGATION",
    "SKILL_AND_TRAINING",
    "SYSTEM_AND_APPLICATION",
    "INTEGRATION_AND_EXTERNAL_SERVICE",
    "DATA_AND_INFORMATION",
    "REPORTING_AND_METRICS",
    "CONTROL_AND_POLICY",
    "CUSTOMER_AND_COMMUNICATION",
    "SERVICE_AND_SUPPORT",
    "TEST_AND_ASSURANCE",
    "PILOT_AND_OPERATIONAL_GUARDRAIL",
}


@dataclass(frozen=True)
class CaseSummary:
    """Verified case dimensions."""

    case_id: str
    component_count: int
    statement_count: int
    entity_count: int
    relationship_count: int
    direct_target_count: int
    direct_collision_count: int
    explicit_unaffected_count: int
    evidence_gap_count: int
    entity_types: Mapping[str, int]
    relationship_types: Mapping[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "component_count": self.component_count,
            "statement_count": self.statement_count,
            "entity_count": self.entity_count,
            "relationship_count": self.relationship_count,
            "direct_target_count": self.direct_target_count,
            "direct_collision_count": self.direct_collision_count,
            "explicit_unaffected_count": self.explicit_unaffected_count,
            "evidence_gap_count": self.evidence_gap_count,
            "entity_types": dict(sorted(self.entity_types.items())),
            "relationship_types": dict(sorted(self.relationship_types.items())),
        }


def _load_json(path: Path) -> Any:
    if path.is_symlink():
        raise SecurityBoundaryError(f"symlink JSON file is not allowed: {path}")
    if not path.is_file():
        raise ValidationError(f"missing JSON file: {path}")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValidationError(f"JSON file exceeds size limit: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON file {path}: {exc}") from exc


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a JSON object")
    return value


def _require_unique(values: Iterable[str], label: str) -> None:
    counts = Counter(values)
    duplicates = sorted(value for value, count in counts.items() if count > 1)
    if duplicates:
        raise ValidationError(f"duplicate {label}: {duplicates}")


def verify_manifest(case_dir: Path) -> None:
    manifest_path = case_dir / "manifest.json"
    manifest = _object(_load_json(manifest_path), "manifest")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValidationError("unsupported manifest schema version")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValidationError("manifest files must be a non-empty list")
    manifest_paths: set[str] = set()
    for raw_entry in entries:
        entry = _object(raw_entry, "manifest entry")
        relative = entry.get("path")
        expected = entry.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValidationError("malformed manifest entry")
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise SecurityBoundaryError(f"unsafe manifest path: {relative}")
        target = case_dir / relative
        if target.is_symlink() or not target.is_file():
            raise ValidationError(f"manifest target missing or unsafe: {relative}")
        actual = sha256_file(target)
        if actual != expected:
            raise ValidationError(
                f"manifest digest mismatch for {relative}: expected {expected}, got {actual}"
            )
        manifest_paths.add(relative)
    actual_json_files = {
        path.relative_to(case_dir).as_posix()
        for path in case_dir.rglob("*.json")
        if path.name != "manifest.json"
    }
    if manifest_paths != actual_json_files:
        missing = sorted(actual_json_files - manifest_paths)
        extra = sorted(manifest_paths - actual_json_files)
        raise ValidationError(f"manifest coverage mismatch: missing={missing}, extra={extra}")


def validate_case(case_dir: Path) -> CaseSummary:
    """Validate the frozen case and return verified dimensions."""

    if case_dir.is_symlink():
        raise SecurityBoundaryError("case directory may not be a symlink")
    case_dir = case_dir.resolve(strict=True)
    verify_manifest(case_dir)

    change_package = _object(_load_json(case_dir / "change-package.json"), "change package")
    entities_payload = _object(_load_json(case_dir / "entities.json"), "entities payload")
    relationships_payload = _object(
        _load_json(case_dir / "relationships.json"), "relationships payload"
    )
    case_metadata = _object(_load_json(case_dir / "case-metadata.json"), "case metadata")

    components = change_package.get("components")
    if not isinstance(components, list) or len(components) != 8:
        raise ValidationError("change package must contain exactly eight components")
    if not all(isinstance(component, dict) for component in components):
        raise ValidationError("every component must be an object")
    component_ids = [component.get("component_id") for component in components]
    if not all(isinstance(value, str) for value in component_ids):
        raise ValidationError("every component requires a string component_id")
    _require_unique(component_ids, "component IDs")

    statements: dict[str, dict[str, Any]] = {}
    evidence_files = sorted((case_dir / "evidence").glob("*.json"))
    if not evidence_files:
        raise ValidationError("evidence directory is empty")
    for evidence_file in evidence_files:
        payload = _object(_load_json(evidence_file), f"evidence document {evidence_file}")
        document_id = payload.get("document_id")
        raw_statements = payload.get("statements")
        if not isinstance(raw_statements, list):
            raise ValidationError(f"statements must be a list in {evidence_file}")
        for raw_statement in raw_statements:
            statement = _object(raw_statement, f"statement in {evidence_file}")
            statement_id = statement.get("statement_id")
            if not isinstance(statement_id, str):
                raise ValidationError(f"statement without ID in {evidence_file}")
            if statement_id in statements:
                raise ValidationError(f"duplicate statement ID: {statement_id}")
            if statement.get("document_id") != document_id:
                raise ValidationError(f"statement document mismatch: {statement_id}")
            text = statement.get("text")
            locator = statement.get("locator")
            classification = statement.get("classification")
            if not all(
                isinstance(value, str) and value for value in (text, locator, classification)
            ):
                raise ValidationError(f"incomplete statement: {statement_id}")
            statements[statement_id] = statement
    if len(statements) < 50:
        raise ValidationError("case requires at least 50 evidence statements")
    if not any(
        statement.get("classification") == "UNTRUSTED_INSTRUCTION_LIKE_TEXT"
        for statement in statements.values()
    ):
        raise ValidationError("prompt-injection negative control statement is missing")

    entities = entities_payload.get("entities")
    if not isinstance(entities, list) or len(entities) < 65:
        raise ValidationError("case requires at least 65 entities")
    if not all(isinstance(entity, dict) for entity in entities):
        raise ValidationError("every entity must be an object")
    entity_ids = [entity.get("entity_id") for entity in entities]
    if not all(isinstance(value, str) for value in entity_ids):
        raise ValidationError("every entity requires a string entity_id")
    _require_unique(entity_ids, "entity IDs")
    entity_by_id = {entity["entity_id"]: entity for entity in entities}
    entity_type_counts: Counter[str] = Counter()
    for entity in entities:
        entity_type = entity.get("entity_type")
        if entity_type not in ENTITY_TYPES:
            raise ValidationError(f"unknown entity type: {entity_type}")
        entity_type_counts[entity_type] += 1
        domain = entity.get("primary_domain")
        if domain not in DOMAIN_CODES:
            raise ValidationError(f"unknown primary domain for {entity['entity_id']}: {domain}")
        evidence_refs = entity.get("source_evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            raise ValidationError(f"entity lacks evidence: {entity['entity_id']}")
        unknown_refs = sorted(set(evidence_refs) - statements.keys())
        if unknown_refs:
            raise ValidationError(
                f"entity has unknown evidence: {entity['entity_id']} {unknown_refs}"
            )
        if entity.get("schema_version") != SCHEMA_VERSION:
            raise ValidationError(f"entity schema mismatch: {entity['entity_id']}")
    missing_entity_types = ENTITY_TYPES - entity_type_counts.keys()
    if missing_entity_types:
        raise ValidationError(f"required entity types missing: {sorted(missing_entity_types)}")
    if set(component_ids) != {
        entity_id
        for entity_id, entity in entity_by_id.items()
        if entity.get("entity_type") == "CHANGE_COMPONENT"
    }:
        raise ValidationError("change component entities do not match the change package")

    relationships = relationships_payload.get("relationships")
    if not isinstance(relationships, list) or len(relationships) < 100:
        raise ValidationError("case requires at least 100 relationships")
    if not all(isinstance(relationship, dict) for relationship in relationships):
        raise ValidationError("every relationship must be an object")
    relationship_ids = [relationship.get("relationship_id") for relationship in relationships]
    if not all(isinstance(value, str) for value in relationship_ids):
        raise ValidationError("every relationship requires a string relationship_id")
    _require_unique(relationship_ids, "relationship IDs")
    relation_type_counts: Counter[str] = Counter()
    direct_origins: defaultdict[str, set[str]] = defaultdict(set)
    for relationship in relationships:
        relationship_id = relationship["relationship_id"]
        source = relationship.get("source_entity_id")
        target = relationship.get("target_entity_id")
        relation_type = relationship.get("relationship_type")
        if source not in entity_by_id or target not in entity_by_id:
            raise ValidationError(f"relationship endpoint missing: {relationship_id}")
        if source == target:
            raise ValidationError(f"self-loop is not allowed: {relationship_id}")
        if relation_type not in RELATION_TYPES:
            raise ValidationError(f"unknown relationship type: {relation_type}")
        relation_type_counts[relation_type] += 1
        evidence_refs = relationship.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            raise ValidationError(f"relationship lacks evidence: {relationship_id}")
        unknown_refs = sorted(set(evidence_refs) - statements.keys())
        if unknown_refs:
            raise ValidationError(
                f"relationship has unknown evidence: {relationship_id} {unknown_refs}"
            )
        condition_id = relationship.get("condition_id")
        if condition_id is not None:
            condition = entity_by_id.get(condition_id)
            if condition is None or condition.get("entity_type") not in {
                "ASSUMPTION",
                "CONSTRAINT",
            }:
                raise ValidationError(f"invalid condition on {relationship_id}: {condition_id}")
        gap_id = relationship.get("evidence_gap_id")
        if gap_id is not None:
            gap = entity_by_id.get(gap_id)
            if gap is None or gap.get("entity_type") != "EVIDENCE_GAP":
                raise ValidationError(f"invalid evidence gap on {relationship_id}: {gap_id}")
        if relationship.get("schema_version") != SCHEMA_VERSION:
            raise ValidationError(f"relationship schema mismatch: {relationship_id}")
        if source in component_ids and relation_type in DIRECT_RELATION_TYPES:
            direct_origins[target].add(source)

    explicit_unaffected = change_package.get("explicitly_unaffected_entity_ids")
    if not isinstance(explicit_unaffected, list) or len(explicit_unaffected) < 6:
        raise ValidationError("at least six explicitly unaffected entities are required")
    for entity_id in explicit_unaffected:
        entity = entity_by_id.get(entity_id)
        if entity is None or entity.get("entity_type") != "NEGATIVE_CONTROL":
            raise ValidationError(f"invalid explicitly unaffected entity: {entity_id}")

    gap_count = entity_type_counts["EVIDENCE_GAP"]
    if gap_count < 3:
        raise ValidationError("at least three deliberate evidence gaps are required")
    collision_count = sum(1 for origins in direct_origins.values() if len(origins) > 1)
    if collision_count < 3:
        raise ValidationError("at least three direct multi-origin collisions are required")

    expected_case_id = case_metadata.get("case_id")
    if change_package.get("case_id") != expected_case_id:
        raise ValidationError("case ID mismatch")

    return CaseSummary(
        case_id=str(expected_case_id),
        component_count=len(components),
        statement_count=len(statements),
        entity_count=len(entities),
        relationship_count=len(relationships),
        direct_target_count=len(direct_origins),
        direct_collision_count=collision_count,
        explicit_unaffected_count=len(explicit_unaffected),
        evidence_gap_count=gap_count,
        entity_types=dict(entity_type_counts),
        relationship_types=dict(relation_type_counts),
    )
