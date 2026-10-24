from datetime import datetime, timezone

import pytest

from domain import (
    ActionType,
    AppState,
    Feeling,
    Patient,
    ReviewStatus,
)
from services import (
    get_open_review,
    mark_seen,
    record_action,
    submit_checkin,
)


@pytest.fixture
def state():
    return AppState(
        scenario_id="test",
        simulated_time=datetime(
            2026, 10, 24, 12, tzinfo=timezone.utc
        ),
        patients={
            "patient-001": Patient(
                "patient-001",
                "Alex Morgan",
                "baseline-001",
            )
        },
    )


def submit_unwell(state, command_id="checkin-1"):
    submit_checkin(
        state,
        command_id=command_id,
        patient_id="patient-001",
        feeling=Feeling.UNWELL,
    )


def test_unwell_creates_review_without_wearable_or_ai(state):
    submit_unwell(state)

    assert not state.windows
    assert not state.assessments
    assert len(state.checkins) == 1
    assert len(state.reviews) == 1

    review = get_open_review(state, "patient-001")

    assert review.status == ReviewStatus.NEW
    assert review.evidence_ids == (next(iter(state.checkins)),)


@pytest.mark.parametrize(
    ("feeling", "symptoms", "expected_reviews"),
    [
        (Feeling.USUAL, (), 0),
        (Feeling.WORSE, (), 1),
        (Feeling.USUAL, ("Chills",), 1),
    ],
)
def test_concern_rules(state, feeling, symptoms, expected_reviews):
    submit_checkin(
        state,
        command_id="checkin-1",
        patient_id="patient-001",
        feeling=feeling,
        symptoms=symptoms,
    )

    assert len(state.reviews) == expected_reviews


def test_repeated_command_does_not_duplicate_records(state):
    submit_unwell(state)
    submit_unwell(state)

    assert len(state.checkins) == 1
    assert len(state.reviews) == 1
    assert len(state.audit_events) == 2


def test_new_evidence_updates_existing_seen_review(state):
    submit_unwell(state)
    review = get_open_review(state, "patient-001")

    mark_seen(
        state,
        command_id="seen-1",
        review_id=review.id,
    )

    submit_checkin(
        state,
        command_id="checkin-2",
        patient_id="patient-001",
        feeling=Feeling.WORSE,
        symptoms=("Chills",),
    )

    updated = state.reviews[review.id]

    assert len(state.reviews) == 1
    assert len(updated.evidence_ids) == 2
    assert updated.status == ReviewStatus.SEEN
    assert state.audit_events[-1].action == "review_evidence_added"


def test_complete_workflow_is_recorded_and_retry_safe(state):
    submit_unwell(state)
    review = get_open_review(state, "patient-001")

    for _ in range(2):
        mark_seen(
            state,
            command_id="seen-1",
            review_id=review.id,
        )

    for _ in range(2):
        record_action(
            state,
            command_id="action-1",
            review_id=review.id,
            action_type=ActionType.CONTACT_ATTEMPTED,
            note="Demo contact attempt recorded.",
        )

    completed = state.reviews[review.id]

    assert completed.status == ReviewStatus.ACTION_RECORDED
    assert completed.action_note == "Demo contact attempt recorded."
    assert get_open_review(state, "patient-001") is None

    assert [event.action for event in state.audit_events] == [
        "checkin_submitted",
        "review_created",
        "review_seen",
        "review_action_recorded",
    ]


def test_action_requires_seen_review_and_note(state):
    submit_unwell(state)
    review = get_open_review(state, "patient-001")

    with pytest.raises(ValueError, match="Mark the review seen"):
        record_action(
            state,
            command_id="action-1",
            review_id=review.id,
            action_type=ActionType.CONTACT_ATTEMPTED,
            note="Demo note.",
        )

    mark_seen(
        state,
        command_id="seen-1",
        review_id=review.id,
    )

    event_count = len(state.audit_events)

    with pytest.raises(ValueError, match="note"):
        record_action(
            state,
            command_id="action-1",
            review_id=review.id,
            action_type=ActionType.CONTACT_ATTEMPTED,
            note="   ",
        )

    assert len(state.audit_events) == event_count
    assert state.reviews[review.id].status == ReviewStatus.SEEN


def test_new_submission_after_action_creates_new_task(state):
    submit_unwell(state)
    first_review = get_open_review(state, "patient-001")

    mark_seen(
        state,
        command_id="seen-1",
        review_id=first_review.id,
    )
    record_action(
        state,
        command_id="action-1",
        review_id=first_review.id,
        action_type=ActionType.CONTACT_ATTEMPTED,
        note="Demo contact attempt.",
    )

    submit_unwell(state, command_id="checkin-2")

    assert len(state.reviews) == 2
    assert get_open_review(state, "patient-001").id != first_review.id