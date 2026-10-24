from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from domain import (
    ActionType,
    AnalysisStatus,
    AppState,
    ConnectionStatus,
    Feeling,
    Patient,
    WearableWindow,
)
from monitoring import (
    AnalysisEngine,
    assess_window,
    monitoring_summary,
)
from services import (
    get_open_review,
    mark_seen,
    record_action,
    submit_checkin,
)


START = datetime(2026, 10, 24, tzinfo=timezone.utc)


class ControlledDetector:
    def __init__(self):
        self.qualifies = True
        self.fail = False

    def score(self, window, *, as_of):
        if self.fail:
            raise RuntimeError("Simulated model failure")

        return SimpleNamespace(
            anomaly_score=0.8 if self.qualifies else 0.4,
            is_anomalous=self.qualifies,
            hr_above_baseline=self.qualifies,
            activity_below_baseline=self.qualifies,
            observed_changes=("Synthetic baseline comparison.",),
        )


@pytest.fixture
def setup():
    state = AppState(
        scenario_id="test",
        simulated_time=START,
        patients={
            "patient-001": Patient(
                "patient-001", "Alex Morgan", "baseline-001"
            )
        },
    )
    detector = ControlledDetector()
    return state, detector, AnalysisEngine(detector=detector)


def window(index):
    start = START + timedelta(hours=4 * index)
    return WearableWindow(
        id=f"window-{index}",
        patient_id="patient-001",
        start=start,
        end=start + timedelta(hours=4),
        resting_hr=85,
        steps=100,
        coverage_percent=95,
        connection=ConnectionStatus.CONNECTED,
    )


def process(state, engine, item):
    assess_window(state, engine, item, as_of=item.end)


def test_two_adjacent_windows_create_one_review(setup):
    state, detector, engine = setup

    process(state, engine, window(0))
    assert not state.reviews

    process(state, engine, window(1))
    assert len(state.reviews) == 1

    review = get_open_review(state, "patient-001")
    assert len(review.evidence_ids) == 2

    process(state, engine, window(2))
    assert len(state.reviews) == 1
    assert len(state.reviews[review.id].evidence_ids) == 3


def test_missing_window_breaks_sequence(setup):
    state, detector, engine = setup

    process(state, engine, window(0))

    missing = replace(
        window(1),
        resting_hr=None,
        steps=None,
        connection=ConnectionStatus.DISCONNECTED,
        coverage_percent=0,
    )
    process(state, engine, missing)
    process(state, engine, window(2))

    assert not state.reviews

    missing_assessment = next(
        item for item in state.assessments.values()
        if item.window_id == missing.id
    )
    assert missing_assessment.anomaly_score is None

    process(state, engine, window(3))
    assert len(state.reviews) == 1


def test_skipped_window_breaks_adjacency(setup):
    state, detector, engine = setup

    process(state, engine, window(0))
    process(state, engine, window(2))

    assert not state.reviews


def test_reprocessing_window_is_noop(setup):
    state, detector, engine = setup

    process(state, engine, window(0))
    process(state, engine, window(0))

    assert len(state.assessments) == 1
    assert len(state.audit_events) == 1


def test_model_failure_does_not_block_patient_concern(setup):
    state, detector, engine = setup
    detector.fail = True

    process(state, engine, window(0))

    assessment = next(iter(state.assessments.values()))
    assert assessment.analysis_status == AnalysisStatus.UNAVAILABLE
    assert assessment.anomaly_score is None

    submit_checkin(
        state,
        command_id="unwell-1",
        patient_id="patient-001",
        feeling=Feeling.UNWELL,
    )

    assert len(state.reviews) == 1
    assert monitoring_summary(
        state, "patient-001"
    )["status"] == "AI analysis unavailable"


def test_disconnect_preserves_review(setup):
    state, detector, engine = setup

    process(state, engine, window(0))
    process(state, engine, window(1))

    disconnected = replace(
        window(2),
        resting_hr=None,
        steps=None,
        coverage_percent=0,
        connection=ConnectionStatus.DISCONNECTED,
    )
    process(state, engine, disconnected)

    assert get_open_review(state, "patient-001") is not None
    assert monitoring_summary(
        state, "patient-001"
    )["status"] == "Monitoring unavailable"


def test_actioned_continuing_episode_does_not_create_repeat_task(setup):
    state, detector, engine = setup

    process(state, engine, window(0))
    process(state, engine, window(1))
    review = get_open_review(state, "patient-001")

    mark_seen(state, command_id="seen-1", review_id=review.id)
    record_action(
        state,
        command_id="action-1",
        review_id=review.id,
        action_type=ActionType.CONTACT_ATTEMPTED,
        note="Demo action.",
    )

    process(state, engine, window(2))
    assert len(state.reviews) == 1
    assert get_open_review(state, "patient-001") is None

    # A valid non-qualifying window ends the episode.
    detector.qualifies = False
    process(state, engine, window(3))

    detector.qualifies = True
    process(state, engine, window(4))
    process(state, engine, window(5))

    assert len(state.reviews) == 2
    assert get_open_review(state, "patient-001") is not None


def test_stale_measurements_have_no_score(setup):
    state, detector, engine = setup
    item = window(0)

    assess_window(
        state,
        engine,
        item,
        as_of=item.end + timedelta(hours=7),
    )

    assessment = next(iter(state.assessments.values()))
    assert assessment.anomaly_score is None
    assert monitoring_summary(
        state, "patient-001"
    )["status"] == "Monitoring unavailable"