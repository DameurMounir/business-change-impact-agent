"""Versioned propagation, attention and obligation rules."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .canonical import canonical_json_bytes, sha256_bytes
from .domain import AttentionTier, ImpactClassification
from .errors import ValidationError


@dataclass(frozen=True)
class PropagationRule:
    relationship_type: str
    direction: str
    minimum_depth: int
    maximum_depth: int
    condition_policy: str
    reason_code: str


@dataclass(frozen=True)
class Rulebook:
    schema_version: str
    maximum_depth: int
    propagation_rules: Mapping[str, PropagationRule]
    attention_entity_types: Mapping[str, AttentionTier]
    attention_domains: Mapping[str, AttentionTier]
    obligation_templates: Mapping[str, Mapping[str, str]]
    digest: str

    def rule_for(self, relationship_type: str) -> PropagationRule | None:
        return self.propagation_rules.get(relationship_type)


def _load(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid rule file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"rule file must be an object: {path}")
    return cast(Mapping[str, Any], value)


def _tier(value: object, label: str) -> AttentionTier:
    try:
        return AttentionTier(str(value))
    except ValueError as exc:
        raise ValidationError(f"invalid attention tier for {label}: {value}") from exc


def load_rulebook(design_dir: Path) -> Rulebook:
    """Load and validate committed deterministic rule files."""

    propagation = _load(design_dir / "propagation-rules.json")
    attention = _load(design_dir / "attention-rules.json")
    obligations = _load(design_dir / "obligation-catalog.json")
    maximum_depth = int(propagation.get("maximum_depth", 0))
    if maximum_depth <= 0 or maximum_depth > 8:
        raise ValidationError("maximum depth must be between one and eight")

    rules: dict[str, PropagationRule] = {}
    raw_rules = propagation.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValidationError("propagation rules must be a non-empty list")
    for raw in raw_rules:
        if not isinstance(raw, dict):
            raise ValidationError("malformed propagation rule")
        relationship_type = str(raw["relationship_type"])
        if relationship_type in rules:
            raise ValidationError(f"duplicate propagation rule: {relationship_type}")
        rule = PropagationRule(
            relationship_type=relationship_type,
            direction=str(raw["direction"]),
            minimum_depth=int(raw["minimum_depth"]),
            maximum_depth=int(raw["maximum_depth"]),
            condition_policy=str(raw["condition_policy"]),
            reason_code=str(raw["reason_code"]),
        )
        if rule.direction != "FORWARD":
            raise ValidationError(f"only explicit forward rules are supported: {relationship_type}")
        if not 2 <= rule.minimum_depth <= rule.maximum_depth <= maximum_depth:
            raise ValidationError(f"invalid depth range for {relationship_type}")
        if rule.condition_policy not in {"ALLOW", "REQUIRE_SEPARATE_CLASSIFICATION"}:
            raise ValidationError(f"invalid condition policy for {relationship_type}")
        rules[relationship_type] = rule

    raw_entity_types = attention.get("entity_type_tiers")
    raw_domains = attention.get("domain_tiers")
    if not isinstance(raw_entity_types, dict) or not isinstance(raw_domains, dict):
        raise ValidationError("attention rule maps are missing")
    entity_types = {str(key): _tier(value, str(key)) for key, value in raw_entity_types.items()}
    domains = {str(key): _tier(value, str(key)) for key, value in raw_domains.items()}

    raw_templates = obligations.get("templates")
    if not isinstance(raw_templates, dict):
        raise ValidationError("obligation templates are missing")
    templates: dict[str, Mapping[str, str]] = {}
    for key, raw in raw_templates.items():
        if not isinstance(raw, dict):
            raise ValidationError(f"malformed obligation template: {key}")
        templates[str(key)] = {str(k): str(v) for k, v in raw.items()}

    digest = sha256_bytes(
        canonical_json_bytes(
            {
                "propagation": propagation,
                "attention": attention,
                "obligations": obligations,
            }
        )
    )
    return Rulebook(
        schema_version=str(propagation["schema_version"]),
        maximum_depth=maximum_depth,
        propagation_rules=rules,
        attention_entity_types=entity_types,
        attention_domains=domains,
        obligation_templates=templates,
        digest=digest,
    )


def attention_for(
    rulebook: Rulebook,
    *,
    entity_type: str,
    domain: str,
    classification: ImpactClassification,
    origin_count: int,
    has_gap: bool,
) -> tuple[AttentionTier, tuple[str, ...]]:
    """Compute a transparent tier and stable reason codes."""

    rank = {
        AttentionTier.LOW: 0,
        AttentionTier.MEDIUM: 1,
        AttentionTier.HIGH: 2,
        AttentionTier.CRITICAL: 3,
    }
    candidates = [
        rulebook.attention_entity_types.get(entity_type, AttentionTier.MEDIUM),
        rulebook.attention_domains.get(domain, AttentionTier.MEDIUM),
    ]
    reasons = [f"ENTITY_TYPE_{entity_type}", f"DOMAIN_{domain}"]
    if classification == ImpactClassification.DIRECT:
        candidates.append(AttentionTier.HIGH)
        reasons.append("DIRECT_CHANGE")
    elif classification == ImpactClassification.CONDITIONAL:
        candidates.append(AttentionTier.HIGH)
        reasons.append("CONDITIONAL_EVIDENCE")
    elif classification == ImpactClassification.EXPLICITLY_UNAFFECTED:
        candidates = [AttentionTier.LOW]
        reasons = ["EXPLICIT_NEGATIVE_CONTROL"]
    else:
        reasons.append("DEPENDENCY_PROPAGATION")
    if origin_count > 1:
        candidates.append(AttentionTier.HIGH)
        reasons.append("MULTI_CHANGE_COLLISION")
    if has_gap:
        candidates.append(AttentionTier.CRITICAL)
        reasons.append("EVIDENCE_GAP")
    return max(candidates, key=rank.__getitem__), tuple(sorted(set(reasons)))
