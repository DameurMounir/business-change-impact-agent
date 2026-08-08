"""Deterministic provider-free demonstration of the complete local vertical."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .canonical import pretty_json
from .domain import ReviewAction
from .errors import ReviewConflictError
from .exporters import write_exports
from .paths import packaged_case_dir, packaged_design_dir
from .service import ImpactAnalysisService
from .store import ReviewStore


def run_demo(workspace: Path, *, reviewer: str) -> Mapping[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    if workspace.is_symlink():
        raise ValueError("demo workspace may not be a symlink")
    result = ImpactAnalysisService(packaged_design_dir()).analyse(packaged_case_dir())
    analysis_path = workspace / "analysis.json"
    analysis_path.write_text(pretty_json(result.as_dict()), encoding="utf-8")
    store = ReviewStore(workspace / "impact-room.sqlite3", clock=lambda: 2_000_000_000.0)
    run_id = "atlasbridge-demo"
    store.create_run(run_id, result)
    challenge = store.issue_challenge(
        run_id,
        result.analysis_digest,
        ttl_seconds=600,
        nonce_factory=lambda: "atlasbridge-demo-review-nonce-000001",
    )
    stale_rejected = False
    try:
        store.record_review(
            run_id=run_id,
            analysis_digest="0" * 64,
            nonce=challenge.nonce,
            reviewer=reviewer,
            action=ReviewAction.CONFIRM,
        )
    except ReviewConflictError:
        stale_rejected = True
    review = store.record_review(
        run_id=run_id,
        analysis_digest=result.analysis_digest,
        nonce=challenge.nonce,
        reviewer=reviewer,
        action=ReviewAction.CONFIRM,
        comment="Confirmed as a synthetic impact-assessment demonstration; no go-live decision made.",
    )
    paths = write_exports(store, run_id, workspace / "exports")
    event_count = store.verify_ledger()
    transcript = {
        "run_id": run_id,
        "analysis_digest": result.analysis_digest,
        "summary": dict(result.summary),
        "stale_review_rejected": stale_rejected,
        "review_id": review.review_id,
        "review_state": review.state.value,
        "verified_ledger_events": event_count,
        "exports": {key: str(value) for key, value in paths.items()},
        "go_live_decision": "NOT_PERFORMED",
    }
    (workspace / "demo-transcript.json").write_text(pretty_json(transcript), encoding="utf-8")
    return transcript
