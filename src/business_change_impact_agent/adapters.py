"""Provider-neutral analysis adapter boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .canonical import canonical_json_bytes, sha256_bytes
from .domain import AnalysisResult, CaseModel
from .engine import analyse_case
from .rulebook import Rulebook


class ImpactAdapter(Protocol):
    """An adapter proposes an analysis; the service remains authoritative."""

    adapter_id: str

    def analyse(self, case: CaseModel, rulebook: Rulebook) -> AnalysisResult: ...


class RuleAdapter:
    """Deterministic provider-free baseline."""

    adapter_id = "deterministic-rule-v1"

    def analyse(self, case: CaseModel, rulebook: Rulebook) -> AnalysisResult:
        return analyse_case(case, rulebook, adapter_id=self.adapter_id)


class FixtureAdapter:
    """Test adapter used to prove fail-closed verification."""

    def __init__(self, result: AnalysisResult, *, adapter_id: str = "fixture-v1") -> None:
        self._result = result
        self.adapter_id = adapter_id

    def analyse(self, case: CaseModel, rulebook: Rulebook) -> AnalysisResult:
        candidate = replace(self._result, adapter_id=self.adapter_id, analysis_digest="")
        digest = sha256_bytes(canonical_json_bytes(candidate.as_dict(include_digest=False)))
        return replace(candidate, analysis_digest=digest)
