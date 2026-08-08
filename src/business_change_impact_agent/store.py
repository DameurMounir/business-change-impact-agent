"""Local SQLite review store with a hash-linked event ledger."""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

from .canonical import canonical_json_bytes, pretty_json, sha256_bytes
from .domain import AnalysisResult, ReviewAction, ReviewState
from .errors import ReviewConflictError, SecurityBoundaryError, ValidationError
from .paths import validate_identifier
from .review import (
    ReviewChallenge,
    ReviewRecord,
    state_for_action,
    validate_comment,
    validate_edits,
    validate_reviewer,
)
from .serialization import analysis_from_dict

Clock = Callable[[], float]
NonceFactory = Callable[[], str]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    analysis_digest TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    state TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS challenges (
    nonce_hash TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    analysis_digest TEXT NOT NULL,
    issued_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    used_at REAL,
    invalidated_at REAL
);
CREATE INDEX IF NOT EXISTS idx_challenges_run ON challenges(run_id);
CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(run_id),
    analysis_digest TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    action TEXT NOT NULL,
    state TEXT NOT NULL,
    comment TEXT NOT NULL,
    edits_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    sequence INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL
);
"""


class ReviewStore:
    """Persist analyses and one terminal human review per run."""

    def __init__(self, path: Path, *, clock: Clock = time.time) -> None:
        self.path = path
        self._clock = clock
        if path.exists() and path.is_symlink():
            raise SecurityBoundaryError(f"review database may not be a symlink: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent.is_symlink():
            raise SecurityBoundaryError(f"review database parent may not be a symlink: {path.parent}")
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
        finally:
            connection.close()

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        created_at: float,
    ) -> str:
        row = connection.execute(
            "SELECT sequence, event_hash FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 1 if row is None else int(row["sequence"]) + 1
        previous_hash = "0" * 64 if row is None else str(row["event_hash"])
        material = {
            "sequence": sequence,
            "run_id": run_id,
            "event_type": event_type,
            "payload": payload,
            "previous_hash": previous_hash,
            "created_at": created_at,
        }
        event_hash = sha256_bytes(canonical_json_bytes(material))
        connection.execute(
            "INSERT INTO events(sequence, run_id, event_type, payload_json, previous_hash, event_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                sequence,
                run_id,
                event_type,
                pretty_json(dict(payload)),
                previous_hash,
                event_hash,
                created_at,
            ),
        )
        return event_hash

    def create_run(self, run_id: str, analysis: AnalysisResult) -> None:
        run_id = validate_identifier(run_id, label="run ID")
        now = self._clock()
        analysis_json = pretty_json(analysis.as_dict())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT analysis_digest, analysis_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["analysis_digest"]) != analysis.analysis_digest
                    or str(existing["analysis_json"]) != analysis_json
                ):
                    connection.execute("ROLLBACK")
                    raise ReviewConflictError("run ID already binds a different analysis")
                connection.execute("COMMIT")
                return
            connection.execute(
                "INSERT INTO runs(run_id, analysis_digest, analysis_json, state, version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 0, ?, ?)",
                (
                    run_id,
                    analysis.analysis_digest,
                    analysis_json,
                    ReviewState.DRAFT.value,
                    now,
                    now,
                ),
            )
            self._append_event(
                connection,
                run_id=run_id,
                event_type="RUN_CREATED",
                payload={"analysis_digest": analysis.analysis_digest},
                created_at=now,
            )
            connection.execute("COMMIT")

    def issue_challenge(
        self,
        run_id: str,
        analysis_digest: str,
        *,
        ttl_seconds: int = 600,
        nonce_factory: NonceFactory = lambda: secrets.token_urlsafe(32),
    ) -> ReviewChallenge:
        run_id = validate_identifier(run_id, label="run ID")
        if not 1 <= ttl_seconds <= 3600:
            raise ValidationError("challenge TTL must be between 1 and 3600 seconds")
        nonce = nonce_factory()
        if not 24 <= len(nonce) <= 256 or any(character.isspace() for character in nonce):
            raise ValidationError("challenge nonce must be 24-256 non-whitespace characters")
        nonce_hash = sha256_bytes(nonce.encode("utf-8"))
        now = self._clock()
        expires_at = now + ttl_seconds
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT analysis_digest, state, version FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run is None:
                connection.execute("ROLLBACK")
                raise ValidationError(f"unknown run ID: {run_id}")
            if str(run["analysis_digest"]) != analysis_digest:
                connection.execute("ROLLBACK")
                raise ReviewConflictError("stale analysis digest")
            state = ReviewState(str(run["state"]))
            if state not in {ReviewState.DRAFT, ReviewState.IN_REVIEW}:
                connection.execute("ROLLBACK")
                raise ReviewConflictError(f"run is already terminal: {state.value}")
            connection.execute(
                "UPDATE challenges SET invalidated_at = ? "
                "WHERE run_id = ? AND used_at IS NULL AND invalidated_at IS NULL",
                (now, run_id),
            )
            version = int(run["version"])
            updated = connection.execute(
                "UPDATE runs SET state = ?, version = version + 1, updated_at = ? "
                "WHERE run_id = ? AND version = ?",
                (ReviewState.IN_REVIEW.value, now, run_id, version),
            )
            if updated.rowcount != 1:
                connection.execute("ROLLBACK")
                raise ReviewConflictError("concurrent review-state update")
            connection.execute(
                "INSERT INTO challenges(nonce_hash, run_id, analysis_digest, issued_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (nonce_hash, run_id, analysis_digest, now, expires_at),
            )
            self._append_event(
                connection,
                run_id=run_id,
                event_type="REVIEW_CHALLENGE_ISSUED",
                payload={
                    "analysis_digest": analysis_digest,
                    "nonce_hash": nonce_hash,
                    "expires_at": expires_at,
                },
                created_at=now,
            )
            connection.execute("COMMIT")
        return ReviewChallenge(run_id, analysis_digest, nonce, expires_at)

    def record_review(
        self,
        *,
        run_id: str,
        analysis_digest: str,
        nonce: str,
        reviewer: str,
        action: ReviewAction,
        comment: str = "",
        edits: Sequence[Mapping[str, object]] = (),
    ) -> ReviewRecord:
        run_id = validate_identifier(run_id, label="run ID")
        reviewer = validate_reviewer(reviewer)
        comment = validate_comment(comment)
        nonce_hash = sha256_bytes(nonce.encode("utf-8"))
        now = self._clock()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT analysis_digest, analysis_json, state, version FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                connection.execute("ROLLBACK")
                raise ValidationError(f"unknown run ID: {run_id}")
            if str(run["analysis_digest"]) != analysis_digest:
                connection.execute("ROLLBACK")
                raise ReviewConflictError("stale analysis digest")
            if ReviewState(str(run["state"])) != ReviewState.IN_REVIEW:
                connection.execute("ROLLBACK")
                raise ReviewConflictError("run is not awaiting review")
            challenge = connection.execute(
                "SELECT run_id, analysis_digest, expires_at, used_at, invalidated_at "
                "FROM challenges WHERE nonce_hash = ?",
                (nonce_hash,),
            ).fetchone()
            if challenge is None or str(challenge["run_id"]) != run_id:
                connection.execute("ROLLBACK")
                raise ReviewConflictError("unknown review challenge")
            if str(challenge["analysis_digest"]) != analysis_digest:
                connection.execute("ROLLBACK")
                raise ReviewConflictError("challenge digest mismatch")
            if challenge["used_at"] is not None:
                connection.execute("ROLLBACK")
                raise ReviewConflictError("review challenge has already been used")
            if challenge["invalidated_at"] is not None:
                connection.execute("ROLLBACK")
                raise ReviewConflictError("review challenge has been superseded")
            if float(challenge["expires_at"]) < now:
                connection.execute("ROLLBACK")
                raise ReviewConflictError("review challenge has expired")

            raw_analysis = json.loads(str(run["analysis_json"]))
            if not isinstance(raw_analysis, dict):
                connection.execute("ROLLBACK")
                raise ValidationError("stored analysis is malformed")
            analysis = analysis_from_dict(cast(Mapping[str, Any], raw_analysis))
            valid_targets = {impact.target_entity_id for impact in analysis.impacts}
            validated_edits = validate_edits(edits, valid_target_ids=valid_targets)
            if action == ReviewAction.EDIT and not validated_edits:
                connection.execute("ROLLBACK")
                raise ValidationError("EDIT requires at least one bounded edit")
            if action != ReviewAction.EDIT and validated_edits:
                connection.execute("ROLLBACK")
                raise ValidationError("bounded edits are allowed only with EDIT")

            state = state_for_action(action)
            review_material = {
                "run_id": run_id,
                "analysis_digest": analysis_digest,
                "reviewer": reviewer,
                "action": action.value,
                "state": state.value,
                "comment": comment,
                "edits": [dict(item) for item in validated_edits],
                "created_at": now,
            }
            review_id = "REV-" + sha256_bytes(canonical_json_bytes(review_material))[:20].upper()
            consumed = connection.execute(
                "UPDATE challenges SET used_at = ? WHERE nonce_hash = ? AND used_at IS NULL",
                (now, nonce_hash),
            )
            if consumed.rowcount != 1:
                connection.execute("ROLLBACK")
                raise ReviewConflictError("concurrent challenge consumption")
            connection.execute(
                "INSERT INTO reviews(review_id, run_id, analysis_digest, reviewer, action, state, "
                "comment, edits_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    review_id,
                    run_id,
                    analysis_digest,
                    reviewer,
                    action.value,
                    state.value,
                    comment,
                    pretty_json([dict(item) for item in validated_edits]),
                    now,
                ),
            )
            version = int(run["version"])
            updated = connection.execute(
                "UPDATE runs SET state = ?, version = version + 1, updated_at = ? "
                "WHERE run_id = ? AND version = ?",
                (state.value, now, run_id, version),
            )
            if updated.rowcount != 1:
                connection.execute("ROLLBACK")
                raise ReviewConflictError("concurrent terminal review")
            self._append_event(
                connection,
                run_id=run_id,
                event_type="HUMAN_REVIEW_RECORDED",
                payload={
                    "review_id": review_id,
                    "analysis_digest": analysis_digest,
                    "reviewer": reviewer,
                    "action": action.value,
                    "state": state.value,
                    "edits": [dict(item) for item in validated_edits],
                },
                created_at=now,
            )
            connection.execute("COMMIT")
        return ReviewRecord(
            review_id=review_id,
            run_id=run_id,
            analysis_digest=analysis_digest,
            reviewer=reviewer,
            action=action,
            state=state,
            comment=comment,
            edits=validated_edits,
            created_at=now,
        )

    def get_snapshot(self, run_id: str) -> Mapping[str, Any]:
        run_id = validate_identifier(run_id, label="run ID")
        with self._connect() as connection:
            run = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if run is None:
                raise ValidationError(f"unknown run ID: {run_id}")
            review = connection.execute(
                "SELECT * FROM reviews WHERE run_id = ?", (run_id,)
            ).fetchone()
        analysis = json.loads(str(run["analysis_json"]))
        if not isinstance(analysis, dict):
            raise ValidationError("stored analysis is malformed")
        review_payload: Mapping[str, Any] | None = None
        if review is not None:
            edits = json.loads(str(review["edits_json"]))
            review_payload = {
                "review_id": str(review["review_id"]),
                "analysis_digest": str(review["analysis_digest"]),
                "reviewer": str(review["reviewer"]),
                "action": str(review["action"]),
                "state": str(review["state"]),
                "comment": str(review["comment"]),
                "edits": edits,
                "created_at": float(review["created_at"]),
            }
        return {
            "run_id": run_id,
            "state": str(run["state"]),
            "version": int(run["version"]),
            "analysis": cast(Mapping[str, Any], analysis),
            "review": review_payload,
        }

    def verify_ledger(self) -> int:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        previous_hash = "0" * 64
        expected_sequence = 1
        for row in rows:
            sequence = int(row["sequence"])
            if sequence != expected_sequence or str(row["previous_hash"]) != previous_hash:
                raise ReviewConflictError("event ledger sequence or previous hash is invalid")
            payload = json.loads(str(row["payload_json"]))
            material = {
                "sequence": sequence,
                "run_id": str(row["run_id"]),
                "event_type": str(row["event_type"]),
                "payload": payload,
                "previous_hash": previous_hash,
                "created_at": float(row["created_at"]),
            }
            actual = sha256_bytes(canonical_json_bytes(material))
            if actual != str(row["event_hash"]):
                raise ReviewConflictError(f"event ledger hash mismatch at sequence {sequence}")
            previous_hash = actual
            expected_sequence += 1
        return len(rows)
