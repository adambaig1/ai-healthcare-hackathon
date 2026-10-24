from collections import Counter

import pytest

from domain import Feeling
from scripts.generate_data import generate_all
from services import submit_checkin
from simulation import (
    advance_four_hours,
    advance_to,
    create_demo,
    run_to_next_event,
)


@pytest.fixture
def fixture_root(tmp_path):
    generate_all(tmp_path)
    return tmp_path


def test_initialisation_processes_one_window_per_patient(fixture_root):
    controller = create_demo(root=fixture_root)
    state = controller.session.state

    assert len(state.assessments) == 3
    assert len(state.processed_window_ids) == 3
    assert not state.checkins
    assert not state.reviews


def test_large_jump_processes_every_window_once(fixture_root):
    controller = create_demo(root=fixture_root)

    advance_to(
        controller,
        controller.session.scenario.end_time,
    )

    state = controller.session.state

    assert len(state.assessments) == 36
    assert len(state.processed_window_ids) == 36

    counts = Counter(
        assessment.patient_id
        for assessment in state.assessments.values()
    )
    assert set(counts.values()) == {12}

    timestamps = [
        assessment.timestamp
        for assessment in state.assessments.values()
    ]
    assert timestamps == sorted(timestamps)

    before = (
        len(state.assessments),
        len(state.reviews),
        len(state.audit_events),
    )

    advance_to(controller, state.simulated_time)

    after = (
        len(state.assessments),
        len(state.reviews),
        len(state.audit_events),
    )

    assert after == before


def test_scripted_concern_is_submitted_only_when_due(fixture_root):
    controller = create_demo("unwell_ordinary", root=fixture_root)
    state = controller.session.state
    scripted = controller.session.scenario.checkins[0]

    assert not state.checkins

    run_to_next_event(controller)

    assert state.simulated_time == scripted.timestamp
    assert state.checkins[scripted.id] == scripted

    matching_reviews = [
        review for review in state.reviews.values()
        if scripted.id in review.evidence_ids
    ]
    assert len(matching_reviews) == 1

    advance_to(controller, state.simulated_time)
    assert len(state.checkins) == 1


def test_four_hour_advance_processes_three_more_windows(fixture_root):
    controller = create_demo(root=fixture_root)

    advance_four_hours(controller)

    assert len(controller.session.state.assessments) == 6


def test_fresh_controller_resets_runtime(fixture_root):
    first = create_demo(root=fixture_root)

    submit_checkin(
        first.session.state,
        command_id="manual-unwell",
        patient_id="patient-001",
        feeling=Feeling.UNWELL,
    )
    advance_four_hours(first)

    fresh = create_demo(root=fixture_root)

    assert not fresh.session.state.checkins
    assert not fresh.session.state.reviews
    assert len(fresh.session.state.assessments) == 3
    assert not fresh.session.state.processed_command_ids
    assert (
        fresh.session.state.simulated_time
        == fresh.session.scenario.initial_time
    )
    assert fresh.engine.detector.threshold == pytest.approx(
        first.engine.detector.threshold
    )


def test_time_cannot_move_backwards(fixture_root):
    controller = create_demo(root=fixture_root)

    with pytest.raises(ValueError, match="backwards"):
        advance_to(
            controller,
            controller.session.scenario.start_time,
        )