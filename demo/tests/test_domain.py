from datetime import datetime, timedelta, timezone

import pytest

from domain import (
    ActionType,
    AnalysisStatus,
    AppState,
    Assessment,
    CheckIn,
    ConnectionStatus,
    DataQuality,
    Feeling,
    ReviewItem,
    ReviewStatus,
    WearableWindow,
)


START = datetime(2026, 10, 24, 8, tzinfo=timezone.utc)
END = START + timedelta(hours=4)


def make_window(**overrides):
    values = {
        "patient_id": "patient-001",
        "start": START,
        "end": END,
        "resting_hr": 70.0,
        "steps": 1000,
        "coverage_percent": 95.0,
        "connection": ConnectionStatus.CONNECTED,
    }
    values.update(overrides)
    return WearableWindow(**values)


def test_missing_values_and_zero_activity_are_distinct():
    missing = make_window(resting_hr=None, steps=None)
    inactive = make_window(steps=0)

    assert missing.resting_hr is None
    assert missing.steps is None
    assert inactive.steps == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"start": START.replace(tzinfo=None)},
        {"end": START + timedelta(hours=3)},
        {"resting_hr": float("nan")},
        {"steps": -1},
        {"coverage_percent": 101.0},
    ],
)
def test_invalid_wearable_values_are_rejected(overrides):
    with pytest.raises(ValueError):
        make_window(**overrides)


def test_unwell_checkin_needs_no_temperature_or_wearable():
    checkin = CheckIn(
        patient_id="patient-001",
        timestamp=END,
        feeling=Feeling.UNWELL,
    )

    assert checkin.temperature_c is None
    assert checkin.symptoms == ()


def test_new_records_have_distinct_ids():
    first = make_window()
    second = make_window()

    assert first.id != second.id


def test_missing_data_cannot_receive_an_ai_score():
    with pytest.raises(ValueError):
        Assessment(
            patient_id="patient-001",
            window_id="window-001",
            timestamp=END,
            data_quality=DataQuality.MISSING,
            analysis_status=AnalysisStatus.SCORED,
            anomaly_score=0.6,
            is_anomalous=True,
        )


def test_ai_failure_can_coexist_with_usable_data():
    assessment = Assessment(
        patient_id="patient-001",
        window_id="window-001",
        timestamp=END,
        data_quality=DataQuality.AVAILABLE,
        analysis_status=AnalysisStatus.UNAVAILABLE,
    )

    assert assessment.anomaly_score is None
    assert assessment.is_anomalous is None
    assert assessment.persistent_change is False


def test_recorded_action_requires_a_nonempty_note():
    with pytest.raises(ValueError):
        ReviewItem(
            patient_id="patient-001",
            reasons=("Patient reported feeling unwell.",),
            evidence_ids=("checkin-001",),
            created_at=START,
            updated_at=END,
            status=ReviewStatus.ACTION_RECORDED,
            seen_at=START,
            action_recorded_at=END,
            action_type=ActionType.CONTACT_ATTEMPTED,
            action_note="   ",
        )


def test_valid_action_completes_the_review_task():
    review = ReviewItem(
        patient_id="patient-001",
        reasons=("Patient reported feeling unwell.",),
        evidence_ids=("checkin-001",),
        created_at=START,
        updated_at=END,
        status=ReviewStatus.ACTION_RECORDED,
        seen_at=START,
        action_recorded_at=END,
        action_type=ActionType.CONTACT_ATTEMPTED,
        action_note="Demo contact attempt recorded.",
    )

    assert review.is_open is False


def test_sessions_do_not_share_mutable_state():
    first = AppState(scenario_id="sustained-change", simulated_time=START)
    second = AppState(scenario_id="sustained-change", simulated_time=START)

    first.processed_window_ids.add("window-001")

    assert second.processed_window_ids == set()