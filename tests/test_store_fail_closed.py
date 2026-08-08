from __future__ import annotations

import sqlite3
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
CASE_DIR = ROOT / "cases" / "atlasbridge"
DESIGN_DIR = ROOT / "design"


def _analysis():
    return ImpactAnalysisService(DESIGN_DIR).analyse(CASE_DIR)


def test_review_store_input_and_state_guards(tmp_path: Path) -> None:
    result = _analysis()
    store = ReviewStore(tmp_path / "review.sqlite3")
    with pytest.raises(ValidationError, match="unknown run ID"):
        store.issue_challenge("missing", result.analysis_digest)

    store.create_run("run", result)
    with pytest.raises(ValidationError, match="TTL"):
        store.issue_challenge("run", result.analysis_digest, ttl_seconds=0)
    with pytest.raises(ValidationError, match="nonce"):
        store.issue_challenge("run", result.analysis_digest, nonce_factory=lambda: "short")
    with pytest.raises(ReviewConflictError, match="stale"):
        store.issue_challenge("run", "0" * 64)

    challenge = store.issue_challenge(
        "run", result.analysis_digest, nonce_factory=lambda: "guard-nonce-00000000000000000001"
    )
    with pytest.raises(ReviewConflictError, match="unknown review challenge"):
        store.record_review(
            run_id="run",
            analysis_digest=result.analysis_digest,
            nonce="unknown-nonce-00000000000000001",
            reviewer="Reviewer",
            action=ReviewAction.CONFIRM,
        )
    with pytest.raises(ValidationError, match="EDIT requires"):
        store.record_review(
            run_id="run",
            analysis_digest=result.analysis_digest,
            nonce=challenge.nonce,
            reviewer="Reviewer",
            action=ReviewAction.EDIT,
        )
    with pytest.raises(ValidationError, match="only with EDIT"):
        store.record_review(
            run_id="run",
            analysis_digest=result.analysis_digest,
            nonce=challenge.nonce,
            reviewer="Reviewer",
            action=ReviewAction.CONFIRM,
            edits=[{"target_entity_id": "STEP-INTAKE", "review_note": "x"}],
        )


def test_review_store_terminal_used_and_malformed_state_guards(tmp_path: Path) -> None:
    result = _analysis()
    db = tmp_path / "review.sqlite3"
    store = ReviewStore(db)
    store.create_run("terminal", result)
    challenge = store.issue_challenge(
        "terminal",
        result.analysis_digest,
        nonce_factory=lambda: "terminal-nonce-000000000000000001",
    )
    store.record_review(
        run_id="terminal",
        analysis_digest=result.analysis_digest,
        nonce=challenge.nonce,
        reviewer="Reviewer",
        action=ReviewAction.CONFIRM,
    )
    with pytest.raises(ReviewConflictError, match="already terminal"):
        store.issue_challenge("terminal", result.analysis_digest)

    with closing(sqlite3.connect(db)) as connection:
        connection.execute(
            "UPDATE runs SET state = ? WHERE run_id = ?",
            (ReviewState.IN_REVIEW.value, "terminal"),
        )
        connection.commit()
    with pytest.raises(ReviewConflictError, match="already been used"):
        store.record_review(
            run_id="terminal",
            analysis_digest=result.analysis_digest,
            nonce=challenge.nonce,
            reviewer="Reviewer",
            action=ReviewAction.CONFIRM,
        )

    store.create_run("malformed", result)
    malformed = store.issue_challenge(
        "malformed",
        result.analysis_digest,
        nonce_factory=lambda: "malformed-nonce-0000000000000001",
    )
    with closing(sqlite3.connect(db)) as connection:
        connection.execute("UPDATE runs SET analysis_json = '[]' WHERE run_id = 'malformed'")
        connection.commit()
    with pytest.raises(ValidationError, match="stored analysis is malformed"):
        store.record_review(
            run_id="malformed",
            analysis_digest=result.analysis_digest,
            nonce=malformed.nonce,
            reviewer="Reviewer",
            action=ReviewAction.CONFIRM,
        )


def test_review_store_snapshot_ledger_and_parent_symlink_guards(tmp_path: Path) -> None:
    result = _analysis()
    db = tmp_path / "review.sqlite3"
    store = ReviewStore(db)
    with pytest.raises(ValidationError, match="unknown run ID"):
        store.get_snapshot("missing")

    store.create_run("snapshot", result)
    with closing(sqlite3.connect(db)) as connection:
        connection.execute("UPDATE runs SET analysis_json = '[]' WHERE run_id = 'snapshot'")
        connection.commit()
    with pytest.raises(ValidationError, match="stored analysis is malformed"):
        store.get_snapshot("snapshot")

    with closing(sqlite3.connect(db)) as connection:
        connection.execute("UPDATE events SET sequence = 2 WHERE sequence = 1")
        connection.commit()
    with pytest.raises(ReviewConflictError, match="sequence or previous hash"):
        store.verify_ledger()

    parent_target = tmp_path / "real-parent"
    parent_target.mkdir()
    parent_link = tmp_path / "linked-parent"
    try:
        parent_link.symlink_to(parent_target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(SecurityBoundaryError, match="parent"):
        ReviewStore(parent_link / "review.sqlite3")
