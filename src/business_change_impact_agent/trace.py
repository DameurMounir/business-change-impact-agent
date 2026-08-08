"""Fail-closed verification of an adapter-produced impact result."""

from __future__ import annotations

from dataclasses import replace

from .canonical import canonical_json_bytes, sha256_bytes
from .domain import AnalysisResult, CaseModel
from .engine import analyse_case
from .errors import ValidationError
from .rulebook import Rulebook


def verify_analysis_result(
    result: AnalysisResult,
    case: CaseModel,
    rulebook: Rulebook,
) -> None:
    """Verify digests and require the evidence-authoritative deterministic result."""

    if result.case_id != case.case_id or result.case_digest != case.case_digest:
        raise ValidationError("analysis does not bind the validated case")
    if result.rulebook_digest != rulebook.digest:
        raise ValidationError("analysis does not bind the committed rulebook")
    expected_digest = sha256_bytes(canonical_json_bytes(result.as_dict(include_digest=False)))
    if expected_digest != result.analysis_digest:
        raise ValidationError("analysis digest mismatch")
    expected = analyse_case(case, rulebook, adapter_id=result.adapter_id)
    normalised_result = replace(result, adapter_id="verified-adapter", analysis_digest="")
    normalised_expected = replace(expected, adapter_id="verified-adapter", analysis_digest="")
    if canonical_json_bytes(normalised_result.as_dict(include_digest=False)) != canonical_json_bytes(
        normalised_expected.as_dict(include_digest=False)
    ):
        raise ValidationError("adapter output differs from the evidence-authoritative graph result")
