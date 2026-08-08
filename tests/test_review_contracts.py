from __future__ import annotations

import pytest

from business_change_impact_agent.domain import ReviewAction, ReviewState
from business_change_impact_agent.errors import ValidationError
from business_change_impact_agent.review import (
    state_for_action,
    validate_comment,
    validate_edits,
    validate_reviewer,
)


def test_every_review_action_has_one_terminal_state() -> None:
    assert {action: state_for_action(action) for action in ReviewAction} == {
        ReviewAction.CONFIRM: ReviewState.CONFIRMED,
        ReviewAction.EDIT: ReviewState.CONFIRMED_WITH_EDITS,
        ReviewAction.REQUEST_REVISION: ReviewState.REVISION_REQUESTED,
        ReviewAction.REJECT: ReviewState.REJECTED,
    }


@pytest.mark.parametrize("value", ["", " " * 4, "x" * 121, "Reviewer\nName"])
def test_reviewer_validation_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValidationError, match="reviewer"):
        validate_reviewer(value)


def test_reviewer_and_comment_are_normalised() -> None:
    assert validate_reviewer("  Reviewer Name  ") == "Reviewer Name"
    assert validate_comment("  bounded comment  ") == "bounded comment"


@pytest.mark.parametrize("value", ["x" * 2001, "bad\x00comment"])
def test_comment_validation_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValidationError, match="review comment"):
        validate_comment(value)


def test_edit_limits_and_forbidden_fields_fail_closed() -> None:
    valid_targets = {"TARGET"}
    with pytest.raises(ValidationError, match="at most 50"):
        validate_edits(
            [{"target_entity_id": "TARGET", "review_note": "x"}] * 51,
            valid_target_ids=valid_targets,
        )
    with pytest.raises(ValidationError, match="forbidden fields"):
        validate_edits(
            [{"target_entity_id": "TARGET", "evidence_refs": ["S-001"]}],
            valid_target_ids=valid_targets,
        )


@pytest.mark.parametrize(
    ("edits", "message"),
    [
        ([{"target_entity_id": "UNKNOWN", "review_note": "x"}], "unknown or duplicated"),
        (
            [
                {"target_entity_id": "TARGET", "review_note": "x"},
                {"target_entity_id": "TARGET", "review_note": "y"},
            ],
            "unknown or duplicated",
        ),
        ([{"target_entity_id": "TARGET"}], "must provide"),
        ([{"target_entity_id": "TARGET", "attention_tier": "UNKNOWN"}], "invalid attention"),
        ([{"target_entity_id": "TARGET", "review_note": "x" * 501}], "exceeds 500"),
        ([{"target_entity_id": "TARGET", "review_note": "bad\x00note"}], "contains NUL"),
    ],
)
def test_edit_shape_validation(edits: list[dict[str, object]], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        validate_edits(edits, valid_target_ids={"TARGET"})


def test_note_only_and_tier_only_edits_are_canonical() -> None:
    validated = validate_edits(
        [
            {"target_entity_id": "A", "review_note": "  retain evidence  "},
            {"target_entity_id": "B", "attention_tier": "HIGH"},
        ],
        valid_target_ids={"A", "B"},
    )
    assert validated == (
        {"target_entity_id": "A", "review_note": "retain evidence"},
        {"target_entity_id": "B", "attention_tier": "HIGH"},
    )
