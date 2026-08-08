"""Application service that validates evidence before and after adapter execution."""

from __future__ import annotations

from pathlib import Path

from .adapters import ImpactAdapter, RuleAdapter
from .case_loader import load_case
from .domain import AnalysisResult
from .rulebook import load_rulebook
from .trace import verify_analysis_result


class ImpactAnalysisService:
    """Controlled, provider-neutral impact analysis service."""

    def __init__(self, design_dir: Path, adapter: ImpactAdapter | None = None) -> None:
        self._design_dir = design_dir
        self._adapter = adapter or RuleAdapter()

    def analyse(self, case_dir: Path) -> AnalysisResult:
        case = load_case(case_dir)
        rulebook = load_rulebook(self._design_dir)
        result = self._adapter.analyse(case, rulebook)
        verify_analysis_result(result, case, rulebook)
        return result
