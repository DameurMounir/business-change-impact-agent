"""Digest-bound human review contracts and bounded edit validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .domain import AttentionTier, ReviewAction, ReviewState
from .errors import ValidationError


@dataclass(frozen=True)
class ReviewChallenge:
    run_id: str
    analysis_digest: str
    nonce: str
    expires_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "analysis_digest": self.analysis_digest,
            "nonce": self.nonce,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class ReviewRecord:
    review_id: str
    run_id: str
    analysis_digest: str
    reviewer: str
    action: ReviewAction
    state: ReviewState
    comment: str
    edits: tuple[Mapping[str, str], ...]
    created_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "run_id": self.run_id,
            "analysis_digest": self.analysis_digest,
            "reviewer": self.reviewer,
            "action": self.action.value,
            "state": self.state.value,
            "comment": self.comment,
            "edits": [dict(edit) for edit in self.edits],
            "created_at": self.created_at,
        }


def state_for_action(action: ReviewAction) -> ReviewState:
    return {
        ReviewAction.CONFIRM: ReviewState.CONFIRMED,
        ReviewAction.EDIT: ReviewState.CONFIRMED_WITH_EDITS,
        ReviewAction.REQUEST_REVISION: ReviewState.REVISION_REQUESTED,
        ReviewAction.REJECT: ReviewState.REJECTED,
    }[action]


def validate_reviewer(value: str) -> str:
    reviewer = value.strip()
    if not reviewer or len(reviewer) > 120 or any(ord(character) < 32 for character in reviewer):
        raise ValidationError("reviewer must be 1-120 printable characters")
    return reviewer


def validate_comment(value: str) -> str:
    comment = value.strip()
    if len(comment) > 2000 or any(character == "\x00" for character in comment):
        raise ValidationError("review comment is invalid or exceeds 2000 characters")
    return comment


def validate_edits(
    edits: Sequence[Mapping[str, object]],
    *,
    valid_target_ids: set[str],
) -> tuple[Mapping[str, str], ...]:
    """Allow only review notes and attention overrides; never mutate evidence or paths."""

    if len(edits) > 50:
        raise ValidationError("at most 50 bounded edits are allowed")
    validated: list[Mapping[str, str]] = []
    seen: set[str] = set()
    for edit in edits:
        allowed = {"target_entity_id", "attention_tier", "review_note"}
        unknown = set(edit) - allowed
        if unknown:
            raise ValidationError(f"edit contains forbidden fields: {sorted(unknown)}")
        target = str(edit.get("target_entity_id", ""))
        if target not in valid_target_ids or target in seen:
            raise ValidationError(f"edit target is unknown or duplicated: {target}")
        seen.add(target)
        tier_raw = edit.get("attention_tier")
        note = str(edit.get("review_note", "")).strip()
        if tier_raw is None and not note:
            raise ValidationError("edit must provide an attention tier or review note")
        result: dict[str, str] = {"target_entity_id": target}
        if tier_raw is not None:
            try:
                result["attention_tier"] = AttentionTier(str(tier_raw)).value
            except ValueError as exc:
                raise ValidationError(f"invalid attention tier for {target}") from exc
        if note:
            if len(note) > 500 or any(character == "\x00" for character in note):
                raise ValidationError("review note exceeds 500 characters or contains NUL")
            result["review_note"] = note
        validated.append(result)
    return tuple(validated)
