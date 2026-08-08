from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

import pytest

from business_change_impact_agent.domain import AttentionTier, ImpactClassification
from business_change_impact_agent.errors import ValidationError
from business_change_impact_agent.rulebook import _load, attention_for, load_rulebook

ROOT = Path(__file__).resolve().parents[1]
DESIGN_DIR = ROOT / "design"


def _copy_design(tmp_path: Path) -> Path:
    target = tmp_path / "design"
    shutil.copytree(DESIGN_DIR, target)
    return target


def _rewrite(path: Path, mutate: Callable[[dict[str, object]], None]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_rule_file_loader_rejects_invalid_and_non_object(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ValidationError, match="invalid rule file"):
        _load(invalid)

    non_object = tmp_path / "list.json"
    non_object.write_text("[]", encoding="utf-8")
    with pytest.raises(ValidationError, match="must be an object"):
        _load(non_object)


@pytest.mark.parametrize(
    ("file_name", "mutate", "message"),
    [
        (
            "propagation-rules.json",
            lambda payload: payload.update({"rules": []}),
            "non-empty list",
        ),
        (
            "propagation-rules.json",
            lambda payload: payload["rules"].__setitem__(0, "bad"),
            "malformed propagation rule",
        ),
        (
            "propagation-rules.json",
            lambda payload: payload["rules"][1].update(
                {"relationship_type": payload["rules"][0]["relationship_type"]}
            ),
            "duplicate propagation rule",
        ),
        (
            "propagation-rules.json",
            lambda payload: payload["rules"][0].update({"direction": "REVERSE"}),
            "only explicit forward",
        ),
        (
            "propagation-rules.json",
            lambda payload: payload["rules"][0].update({"minimum_depth": 1}),
            "invalid depth range",
        ),
        (
            "propagation-rules.json",
            lambda payload: payload["rules"][0].update({"condition_policy": "UNKNOWN"}),
            "invalid condition policy",
        ),
        (
            "attention-rules.json",
            lambda payload: payload.update({"entity_type_tiers": []}),
            "attention rule maps are missing",
        ),
        (
            "attention-rules.json",
            lambda payload: payload["entity_type_tiers"].update({"ROLE": "UNKNOWN"}),
            "invalid attention tier",
        ),
        (
            "obligation-catalog.json",
            lambda payload: payload.update({"templates": []}),
            "obligation templates are missing",
        ),
        (
            "obligation-catalog.json",
            lambda payload: payload["templates"].__setitem__("ROLE", "bad"),
            "malformed obligation template",
        ),
    ],
)
def test_rulebook_mutations_fail_closed(
    tmp_path: Path,
    file_name: str,
    mutate: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    design = _copy_design(tmp_path)
    _rewrite(design / file_name, mutate)
    with pytest.raises(ValidationError, match=message):
        load_rulebook(design)


def test_attention_branches_are_explicit() -> None:
    rulebook = load_rulebook(DESIGN_DIR)
    indirect_tier, indirect_reasons = attention_for(
        rulebook,
        entity_type="UNKNOWN_ENTITY_TYPE",
        domain="UNKNOWN_DOMAIN",
        classification=ImpactClassification.INDIRECT,
        origin_count=1,
        has_gap=False,
    )
    assert indirect_tier == AttentionTier.MEDIUM
    assert "DEPENDENCY_PROPAGATION" in indirect_reasons

    conditional_tier, conditional_reasons = attention_for(
        rulebook,
        entity_type="EXTERNAL_SERVICE",
        domain="INTEGRATION_AND_EXTERNAL_SERVICE",
        classification=ImpactClassification.CONDITIONAL,
        origin_count=1,
        has_gap=True,
    )
    assert conditional_tier == AttentionTier.CRITICAL
    assert {"CONDITIONAL_EVIDENCE", "EVIDENCE_GAP"} <= set(conditional_reasons)
