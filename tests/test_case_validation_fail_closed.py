from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pytest

from business_change_impact_agent.case_validation import (
    DIRECT_RELATION_TYPES,
    MAX_JSON_BYTES,
    _load_json,
    validate_case,
    verify_manifest,
)
from business_change_impact_agent.errors import SecurityBoundaryError, ValidationError

ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "cases" / "atlasbridge"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _copy_case(tmp_path: Path) -> Path:
    target = tmp_path / "case"
    shutil.copytree(CASE_DIR, target)
    return target


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _refresh_manifest(case_dir: Path) -> None:
    original = _load(case_dir / "manifest.json")
    entries = []
    for path in sorted(case_dir.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        data = path.read_bytes()
        entries.append(
            {
                "path": path.relative_to(case_dir).as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        )
    original["files"] = entries
    _write_json(case_dir / "manifest.json", original)


def _mutate_case(case_dir: Path, mutation: str) -> None:
    package_path = case_dir / "change-package.json"
    entities_path = case_dir / "entities.json"
    relationships_path = case_dir / "relationships.json"
    metadata_path = case_dir / "case-metadata.json"
    package = _load(package_path)
    entities_payload = _load(entities_path)
    relationships_payload = _load(relationships_path)
    metadata = _load(metadata_path)

    if mutation == "component-count":
        package["components"].pop()
        _write_json(package_path, package)
    elif mutation == "component-object":
        package["components"][0] = "not-an-object"
        _write_json(package_path, package)
    elif mutation == "component-id-type":
        package["components"][0]["component_id"] = 7
        _write_json(package_path, package)
    elif mutation == "component-id-duplicate":
        package["components"][1]["component_id"] = package["components"][0]["component_id"]
        _write_json(package_path, package)
    elif mutation == "evidence-empty":
        shutil.rmtree(case_dir / "evidence")
        (case_dir / "evidence").mkdir()
    elif mutation.startswith("statement-") or mutation == "injection-missing":
        doc_paths = sorted((case_dir / "evidence").glob("*.json"))
        first_path = doc_paths[0]
        first = _load(first_path)
        if mutation == "statement-list":
            first["statements"] = "not-a-list"
            _write_json(first_path, first)
        elif mutation == "statement-object":
            first["statements"][0] = "not-an-object"
            _write_json(first_path, first)
        elif mutation == "statement-id-type":
            first["statements"][0]["statement_id"] = None
            _write_json(first_path, first)
        elif mutation == "statement-id-duplicate":
            first["statements"][1]["statement_id"] = first["statements"][0]["statement_id"]
            _write_json(first_path, first)
        elif mutation == "statement-document-mismatch":
            first["statements"][0]["document_id"] = "DOC-X"
            _write_json(first_path, first)
        elif mutation == "statement-incomplete":
            first["statements"][0]["text"] = ""
            _write_json(first_path, first)
        elif mutation == "statement-count":
            remaining = 49
            for path in doc_paths:
                payload = _load(path)
                rows = payload["statements"]
                keep = min(len(rows), remaining)
                payload["statements"] = rows[:keep]
                remaining -= keep
                _write_json(path, payload)
        elif mutation == "injection-missing":
            for path in doc_paths:
                payload = _load(path)
                for statement in payload["statements"]:
                    if statement["classification"] == "UNTRUSTED_INSTRUCTION_LIKE_TEXT":
                        statement["classification"] = "AUTHORISED_SYNTHETIC_EVIDENCE"
                _write_json(path, payload)
        else:  # pragma: no cover - parameter table protects this branch
            raise AssertionError(mutation)
    elif mutation == "entity-count":
        entities_payload["entities"] = entities_payload["entities"][:64]
        _write_json(entities_path, entities_payload)
    elif mutation == "entity-object":
        entities_payload["entities"][0] = "not-an-object"
        _write_json(entities_path, entities_payload)
    elif mutation == "entity-id-type":
        entities_payload["entities"][0]["entity_id"] = None
        _write_json(entities_path, entities_payload)
    elif mutation == "entity-id-duplicate":
        entities_payload["entities"][1]["entity_id"] = entities_payload["entities"][0]["entity_id"]
        _write_json(entities_path, entities_payload)
    elif mutation == "entity-type":
        entities_payload["entities"][0]["entity_type"] = "UNKNOWN"
        _write_json(entities_path, entities_payload)
    elif mutation == "entity-domain":
        entities_payload["entities"][0]["primary_domain"] = "UNKNOWN"
        _write_json(entities_path, entities_payload)
    elif mutation == "entity-evidence-empty":
        entities_payload["entities"][0]["source_evidence_refs"] = []
        _write_json(entities_path, entities_payload)
    elif mutation == "entity-evidence-unknown":
        entities_payload["entities"][0]["source_evidence_refs"] = ["S-999"]
        _write_json(entities_path, entities_payload)
    elif mutation == "entity-schema":
        entities_payload["entities"][0]["schema_version"] = "9.0.0"
        _write_json(entities_path, entities_payload)
    elif mutation == "entity-type-missing":
        counts = Counter(item["entity_type"] for item in entities_payload["entities"])
        unique_type = next(
            key for key, count in counts.items() if count == 1 and key != "CHANGE_COMPONENT"
        )
        entity = next(
            item for item in entities_payload["entities"] if item["entity_type"] == unique_type
        )
        entity["entity_type"] = "PROCESS"
        _write_json(entities_path, entities_payload)
    elif mutation == "component-entity-mismatch":
        next(
            item for item in entities_payload["entities"] if item["entity_id"] == "CC-01"
        )["entity_type"] = "PROCESS"
        _write_json(entities_path, entities_payload)
    elif mutation == "relationship-count":
        relationships_payload["relationships"] = relationships_payload["relationships"][:99]
        _write_json(relationships_path, relationships_payload)
    elif mutation == "relationship-object":
        relationships_payload["relationships"][0] = "not-an-object"
        _write_json(relationships_path, relationships_payload)
    elif mutation == "relationship-id-type":
        relationships_payload["relationships"][0]["relationship_id"] = None
        _write_json(relationships_path, relationships_payload)
    elif mutation == "relationship-id-duplicate":
        relationships_payload["relationships"][1]["relationship_id"] = relationships_payload[
            "relationships"
        ][0]["relationship_id"]
        _write_json(relationships_path, relationships_payload)
    elif mutation == "relationship-endpoint":
        relationships_payload["relationships"][0]["target_entity_id"] = "MISSING"
        _write_json(relationships_path, relationships_payload)
    elif mutation == "relationship-self-loop":
        row = relationships_payload["relationships"][0]
        row["target_entity_id"] = row["source_entity_id"]
        _write_json(relationships_path, relationships_payload)
    elif mutation == "relationship-type":
        relationships_payload["relationships"][0]["relationship_type"] = "UNKNOWN"
        _write_json(relationships_path, relationships_payload)
    elif mutation == "relationship-evidence-empty":
        relationships_payload["relationships"][0]["evidence_refs"] = []
        _write_json(relationships_path, relationships_payload)
    elif mutation == "relationship-evidence-unknown":
        relationships_payload["relationships"][0]["evidence_refs"] = ["S-999"]
        _write_json(relationships_path, relationships_payload)
    elif mutation == "relationship-condition":
        row = next(
            item
            for item in relationships_payload["relationships"]
            if item["condition_id"] is not None
        )
        row["condition_id"] = "CC-01"
        _write_json(relationships_path, relationships_payload)
    elif mutation == "relationship-gap":
        row = next(
            item
            for item in relationships_payload["relationships"]
            if item["evidence_gap_id"] is not None
        )
        row["evidence_gap_id"] = "CC-01"
        _write_json(relationships_path, relationships_payload)
    elif mutation == "relationship-schema":
        relationships_payload["relationships"][0]["schema_version"] = "9.0.0"
        _write_json(relationships_path, relationships_payload)
    elif mutation == "unaffected-count":
        package["explicitly_unaffected_entity_ids"] = package[
            "explicitly_unaffected_entity_ids"
        ][:5]
        _write_json(package_path, package)
    elif mutation == "unaffected-invalid":
        package["explicitly_unaffected_entity_ids"][0] = "CC-01"
        _write_json(package_path, package)
    elif mutation == "gap-count":
        gaps = [
            item
            for item in entities_payload["entities"]
            if item["entity_type"] == "EVIDENCE_GAP"
        ]
        changed, replacement = gaps[0], gaps[1]
        changed["entity_type"] = "ASSUMPTION"
        for relationship in relationships_payload["relationships"]:
            if relationship["evidence_gap_id"] == changed["entity_id"]:
                relationship["evidence_gap_id"] = replacement["entity_id"]
        _write_json(entities_path, entities_payload)
        _write_json(relationships_path, relationships_payload)
    elif mutation == "collision-count":
        rows = relationships_payload["relationships"]
        origins: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        component_ids = {item["component_id"] for item in package["components"]}
        for row in rows:
            if (
                row["source_entity_id"] in component_ids
                and row["relationship_type"] in DIRECT_RELATION_TYPES
            ):
                origins[row["target_entity_id"]].append(row)
        for collision_rows in origins.values():
            for row in collision_rows[1:]:
                row["relationship_type"] = "CONTAINS"
        _write_json(relationships_path, relationships_payload)
    elif mutation == "case-id":
        metadata["case_id"] = "OTHER-CASE"
        _write_json(metadata_path, metadata)
    else:  # pragma: no cover - parameter table protects this branch
        raise AssertionError(mutation)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("component-count", "exactly eight"),
        ("component-object", "component must be an object"),
        ("component-id-type", "string component_id"),
        ("component-id-duplicate", "duplicate component IDs"),
        ("evidence-empty", "evidence directory is empty"),
        ("statement-list", "statements must be a list"),
        ("statement-object", "statement .* must be a JSON object"),
        ("statement-id-type", "statement without ID"),
        ("statement-id-duplicate", "duplicate statement ID"),
        ("statement-document-mismatch", "statement document mismatch"),
        ("statement-incomplete", "incomplete statement"),
        ("statement-count", "at least 50"),
        ("injection-missing", "negative control statement is missing"),
        ("entity-count", "at least 65 entities"),
        ("entity-object", "entity must be an object"),
        ("entity-id-type", "string entity_id"),
        ("entity-id-duplicate", "duplicate entity IDs"),
        ("entity-type", "unknown entity type"),
        ("entity-domain", "unknown primary domain"),
        ("entity-evidence-empty", "entity lacks evidence"),
        ("entity-evidence-unknown", "entity has unknown evidence"),
        ("entity-schema", "entity schema mismatch"),
        ("entity-type-missing", "required entity types missing"),
        ("component-entity-mismatch", "change component entities do not match"),
        ("relationship-count", "at least 100 relationships"),
        ("relationship-object", "relationship must be an object"),
        ("relationship-id-type", "string relationship_id"),
        ("relationship-id-duplicate", "duplicate relationship IDs"),
        ("relationship-endpoint", "relationship endpoint missing"),
        ("relationship-self-loop", "self-loop is not allowed"),
        ("relationship-type", "unknown relationship type"),
        ("relationship-evidence-empty", "relationship lacks evidence"),
        ("relationship-evidence-unknown", "relationship has unknown evidence"),
        ("relationship-condition", "invalid condition"),
        ("relationship-gap", "invalid evidence gap"),
        ("relationship-schema", "relationship schema mismatch"),
        ("unaffected-count", "six explicitly unaffected"),
        ("unaffected-invalid", "invalid explicitly unaffected"),
        ("gap-count", "three deliberate evidence gaps"),
        ("collision-count", "three direct multi-origin collisions"),
        ("case-id", "case ID mismatch"),
    ],
)
def test_case_mutations_fail_closed(
    tmp_path: Path, mutation: str, message: str
) -> None:
    target = _copy_case(tmp_path)
    _mutate_case(target, mutation)
    _refresh_manifest(target)
    with pytest.raises(ValidationError, match=message):
        validate_case(target)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "manifest must be a JSON object"),
        ({"schema_version": "9.0.0", "files": []}, "unsupported manifest schema"),
        ({"schema_version": "1.0.0", "files": []}, "non-empty list"),
        ({"schema_version": "1.0.0", "files": ["bad"]}, "manifest entry must"),
        (
            {"schema_version": "1.0.0", "files": [{"path": 7, "sha256": None}]},
            "malformed manifest entry",
        ),
    ],
)
def test_manifest_shape_is_fail_closed(
    tmp_path: Path, payload: object, message: str
) -> None:
    target = _copy_case(tmp_path)
    _write_json(target / "manifest.json", payload)
    with pytest.raises(ValidationError, match=message):
        verify_manifest(target)


def test_manifest_rejects_missing_target_and_coverage_drift(tmp_path: Path) -> None:
    target = _copy_case(tmp_path)
    manifest = _load(target / "manifest.json")
    manifest["files"][0]["path"] = "missing.json"
    _write_json(target / "manifest.json", manifest)
    with pytest.raises(ValidationError, match="target missing"):
        verify_manifest(target)

    target = _copy_case(tmp_path / "second")
    extra = target / "unlisted.json"
    _write_json(extra, {"x": 1})
    with pytest.raises(ValidationError, match="coverage mismatch"):
        verify_manifest(target)


def test_json_loader_rejects_missing_invalid_large_and_symlink(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="missing JSON file"):
        _load_json(tmp_path / "missing.json")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ValidationError, match="invalid JSON file"):
        _load_json(invalid)

    large = tmp_path / "large.json"
    large.write_bytes(b" " * (MAX_JSON_BYTES + 1))
    with pytest.raises(ValidationError, match="size limit"):
        _load_json(large)

    target = tmp_path / "target.json"
    _write_json(target, {"ok": True})
    link = tmp_path / "link.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(SecurityBoundaryError, match="symlink JSON"):
        _load_json(link)


def test_case_directory_symlink_is_rejected(tmp_path: Path) -> None:
    target = _copy_case(tmp_path)
    link = tmp_path / "case-link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(SecurityBoundaryError, match="case directory"):
        validate_case(link)
