from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from contextlib import closing
from pathlib import Path

import pytest

from business_change_impact_agent.domain import ReviewAction, ReviewState
from business_change_impact_agent.errors import (
    ReviewConflictError,
    SecurityBoundaryError,
    ValidationError,
)
from business_change_impact_agent.service import ImpactAnalysisService
from business_change_impact_agent.store import ReviewStore

ROOT = Path(__file__).resolve().parents[1]


class MutableClock:
    def __init__(self, value: float = 1_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def analysis():
    return ImpactAnalysisService(ROOT / "design").analyse(ROOT / "cases" / "atlasbridge")


def test_stale_digest_replay_and_terminal_state_are_rejected(tmp_path: Path) -> None:
    clock = MutableClock()
    store = ReviewStore(tmp_path / "review.sqlite3", clock=clock)
    result = analysis()
    store.create_run("run-1", result)
    challenge = store.issue_challenge(
        "run-1", result.analysis_digest, nonce_factory=lambda: "review-nonce-000000000000000001"
    )
    with pytest.raises(ReviewConflictError, match="stale"):
        store.record_review(
            run_id="run-1",
            analysis_digest="0" * 64,
            nonce=challenge.nonce,
            reviewer="Reviewer",
            action=ReviewAction.CONFIRM,
        )
    record = store.record_review(
        run_id="run-1",
        analysis_digest=result.analysis_digest,
        nonce=challenge.nonce,
        reviewer="Reviewer",
        action=ReviewAction.CONFIRM,
        comment="Confirmed for synthetic demonstration only.",
    )
    assert record.state == ReviewState.CONFIRMED
    with pytest.raises(ReviewConflictError):
        store.record_review(
            run_id="run-1",
            analysis_digest=result.analysis_digest,
            nonce=challenge.nonce,
            reviewer="Reviewer",
            action=ReviewAction.CONFIRM,
        )
    assert store.verify_ledger() == 3


def test_expired_and_superseded_challenges_fail(tmp_path: Path) -> None:
    clock = MutableClock()
    store = ReviewStore(tmp_path / "review.sqlite3", clock=clock)
    result = analysis()
    store.create_run("expired", result)
    expired = store.issue_challenge(
        "expired",
        result.analysis_digest,
        ttl_seconds=1,
        nonce_factory=lambda: "expired-nonce-000000000000000001",
    )
    clock.value += 2
    with pytest.raises(ReviewConflictError, match="expired"):
        store.record_review(
            run_id="expired",
            analysis_digest=result.analysis_digest,
            nonce=expired.nonce,
            reviewer="Reviewer",
            action=ReviewAction.REJECT,
        )

    store.create_run("superseded", result)
    first = store.issue_challenge(
        "superseded",
        result.analysis_digest,
        nonce_factory=lambda: "superseded-nonce-00000000000001",
    )
    second = store.issue_challenge(
        "superseded",
        result.analysis_digest,
        nonce_factory=lambda: "replacement-nonce-000000000000001",
    )
    with pytest.raises(ReviewConflictError, match="superseded"):
        store.record_review(
            run_id="superseded",
            analysis_digest=result.analysis_digest,
            nonce=first.nonce,
            reviewer="Reviewer",
            action=ReviewAction.REJECT,
        )
    assert (
        store.record_review(
            run_id="superseded",
            analysis_digest=result.analysis_digest,
            nonce=second.nonce,
            reviewer="Reviewer",
            action=ReviewAction.REQUEST_REVISION,
        ).state
        == ReviewState.REVISION_REQUESTED
    )


def test_bounded_edit_cannot_change_evidence_or_paths(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    result = analysis()
    store.create_run("edit-run", result)
    challenge = store.issue_challenge(
        "edit-run",
        result.analysis_digest,
        nonce_factory=lambda: "bounded-edit-nonce-00000000000001",
    )
    record = store.record_review(
        run_id="edit-run",
        analysis_digest=result.analysis_digest,
        nonce=challenge.nonce,
        reviewer="Reviewer",
        action=ReviewAction.EDIT,
        edits=[
            {
                "target_entity_id": "EXT-SCREENING",
                "attention_tier": "HIGH",
                "review_note": "Keep conditional until vendor evidence is retained.",
            }
        ],
    )
    assert record.state == ReviewState.CONFIRMED_WITH_EDITS

    store.create_run("bad-edit", result)
    bad = store.issue_challenge(
        "bad-edit",
        result.analysis_digest,
        nonce_factory=lambda: "bad-edit-review-nonce-0000000001",
    )
    with pytest.raises(ValidationError, match="forbidden fields"):
        store.record_review(
            run_id="bad-edit",
            analysis_digest=result.analysis_digest,
            nonce=bad.nonce,
            reviewer="Reviewer",
            action=ReviewAction.EDIT,
            edits=[{"target_entity_id": "EXT-SCREENING", "evidence_refs": ["S-999"]}],
        )


def test_concurrent_double_confirmation_has_one_winner(tmp_path: Path) -> None:
    db = tmp_path / "review.sqlite3"
    result = analysis()
    store = ReviewStore(db)
    store.create_run("concurrent", result)
    challenge = store.issue_challenge(
        "concurrent",
        result.analysis_digest,
        nonce_factory=lambda: "concurrent-review-nonce-0000000001",
    )

    def attempt() -> str:
        try:
            ReviewStore(db).record_review(
                run_id="concurrent",
                analysis_digest=result.analysis_digest,
                nonce=challenge.nonce,
                reviewer="Reviewer",
                action=ReviewAction.CONFIRM,
            )
            return "confirmed"
        except ReviewConflictError:
            return "blocked"

    pool = ThreadPoolExecutor(max_workers=2)
    futures = [pool.submit(attempt) for _ in range(2)]
    try:
        outcomes = [future.result(timeout=20) for future in futures]
    except FuturesTimeoutError as exc:
        raise AssertionError("concurrent review attempts exceeded the bounded timeout") from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    assert sorted(outcomes) == ["blocked", "confirmed"]


def test_ledger_tampering_is_detected(tmp_path: Path) -> None:
    db = tmp_path / "review.sqlite3"
    store = ReviewStore(db)
    result = analysis()
    store.create_run("tamper", result)
    assert store.verify_ledger() == 1
    with closing(sqlite3.connect(db)) as connection:
        connection.execute("UPDATE events SET payload_json = ? WHERE sequence = 1", ('{"x":1}',))
        connection.commit()
    with pytest.raises(ReviewConflictError, match="hash mismatch"):
        store.verify_ledger()


def test_run_id_conflict_and_database_symlink_are_rejected(tmp_path: Path) -> None:
    result = analysis()
    store = ReviewStore(tmp_path / "review.sqlite3")
    store.create_run("same", result)
    store.create_run("same", result)
    changed = result.__class__(**{**result.__dict__, "analysis_digest": "f" * 64})
    with pytest.raises(ReviewConflictError, match="different analysis"):
        store.create_run("same", changed)
    target = tmp_path / "target.sqlite3"
    target.touch()
    link = tmp_path / "link.sqlite3"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(SecurityBoundaryError):
        ReviewStore(link)
