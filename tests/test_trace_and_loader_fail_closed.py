from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

import business_change_impact_agent.case_loader as case_loader
from business_change_impact_agent.canonical import canonical_json_bytes, sha256_bytes
from business_change_impact_agent.errors import ValidationError
from business_change_impact_agent.rulebook import load_rulebook
from business_change_impact_agent.service import ImpactAnalysisService
from business_change_impact_agent.trace import verify_analysis_result

ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "cases" / "atlasbridge"
DESIGN_DIR = ROOT / "design"


def _analysis():
    return ImpactAnalysisService(DESIGN_DIR).analyse(CASE_DIR)


def test_trace_verifier_rejects_case_rulebook_and_digest_drift() -> None:
    result = _analysis()
    case = case_loader.load_case(CASE_DIR)
    rulebook = load_rulebook(DESIGN_DIR)

    with pytest.raises(ValidationError, match="validated case"):
        verify_analysis_result(replace(result, case_id="OTHER"), case, rulebook)
    with pytest.raises(ValidationError, match="committed rulebook"):
        verify_analysis_result(replace(result, rulebook_digest="0" * 64), case, rulebook)
    with pytest.raises(ValidationError, match="digest mismatch"):
        verify_analysis_result(replace(result, analysis_digest="0" * 64), case, rulebook)


def test_trace_verifier_rejects_recomputed_but_non_authoritative_result() -> None:
    result = _analysis()
    case = case_loader.load_case(CASE_DIR)
    rulebook = load_rulebook(DESIGN_DIR)
    changed = replace(result, summary={**result.summary, "direct": 999}, analysis_digest="")
    changed = replace(
        changed,
        analysis_digest=sha256_bytes(canonical_json_bytes(changed.as_dict(include_digest=False))),
    )
    with pytest.raises(ValidationError, match="differs from"):
        verify_analysis_result(changed, case, rulebook)


def test_case_loader_private_shape_guards(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ValidationError, match="cannot read"):
        case_loader._read_object(invalid)

    non_object = tmp_path / "list.json"
    non_object.write_text("[]", encoding="utf-8")
    with pytest.raises(ValidationError, match="expected JSON object"):
        case_loader._read_object(non_object)

    with pytest.raises(ValidationError, match="string list"):
        case_loader._strings(["ok", 7], "test values")


def test_case_loader_rejects_malformed_validated_payloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "case"
    shutil.copytree(CASE_DIR, target)
    monkeypatch.setattr(case_loader, "validate_case", lambda _path: None)

    evidence = target / "evidence" / "doc-01.json"
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["statements"] = "bad"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="statements missing"):
        case_loader.load_case(target)

    shutil.rmtree(target)
    shutil.copytree(CASE_DIR, target)
    payload = json.loads((target / "change-package.json").read_text(encoding="utf-8"))
    payload["components"] = "bad"
    (target / "change-package.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="components must be a list"):
        case_loader.load_case(target)
