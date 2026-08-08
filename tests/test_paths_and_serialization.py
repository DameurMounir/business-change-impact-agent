from __future__ import annotations

from pathlib import Path

import pytest

from business_change_impact_agent.errors import SecurityBoundaryError, ValidationError
from business_change_impact_agent.paths import ensure_safe_child, validate_identifier
from business_change_impact_agent.serialization import analysis_from_dict
from business_change_impact_agent.service import ImpactAnalysisService

ROOT = Path(__file__).resolve().parents[1]


def test_safe_identifiers_and_children(tmp_path: Path) -> None:
    assert validate_identifier("run-01.ok") == "run-01.ok"
    with pytest.raises(SecurityBoundaryError):
        validate_identifier("../escape")
    child = ensure_safe_child(tmp_path, Path("child/file.json"))
    assert child == tmp_path / "child" / "file.json"
    with pytest.raises(SecurityBoundaryError):
        ensure_safe_child(tmp_path, Path("../outside"))


def test_analysis_serialization_round_trip_and_rejects_malformed() -> None:
    result = ImpactAnalysisService(ROOT / "design").analyse(ROOT / "cases" / "atlasbridge")
    parsed = analysis_from_dict(result.as_dict())
    assert parsed.as_dict() == result.as_dict()
    malformed = result.as_dict()
    malformed["impacts"] = "not-a-list"
    with pytest.raises(ValidationError):
        analysis_from_dict(malformed)
