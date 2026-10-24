from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest

from data import create_session
from detector import feature_matrix, train_detector
from domain import ConnectionStatus
from scripts.generate_data import generate_all


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp("detector-fixtures")
    generate_all(root)

    session = create_session(root=root)
    detector = train_detector(
        session.reference,
        session.calibration,
    )

    return session, detector


def test_baselines_cover_every_patient_and_slot(prepared):
    session, detector = prepared

    assert len(detector.baselines) == 3 * 6

    for baseline in detector.baselines.values():
        assert baseline.sample_count == 14
        assert baseline.hr_spread >= detector.settings.min_hr_mad_bpm
        assert (
            baseline.log_steps_spread
            >= detector.settings.min_log_steps_mad
        )


def test_threshold_uses_calibration_percentile(prepared):
    session, detector = prepared

    features = feature_matrix(
        session.calibration,
        detector.baselines,
    )
    scores = -detector.model.score_samples(features)

    expected = np.percentile(
        scores,
        detector.settings.threshold_percentile,
    )

    assert detector.threshold == pytest.approx(expected)


def test_inference_is_finite_and_reproducible(prepared):
    session, detector = prepared
    window = session.scenario.windows[0]

    first = detector.score(window, as_of=window.end)
    second = detector.score(window, as_of=window.end)

    assert first == second
    assert np.isfinite(first.anomaly_score)
    assert first.is_anomalous == (
        first.anomaly_score > detector.threshold
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"resting_hr": None},
        {"steps": None},
        {"coverage_percent": None},
        {"coverage_percent": 20.0},
        {"connection": ConnectionStatus.DISCONNECTED},
    ],
)
def test_unusable_measurements_are_not_scored(prepared, changes):
    session, detector = prepared
    window = replace(session.scenario.windows[0], **changes)

    with pytest.raises(ValueError):
        detector.score(window, as_of=window.end)


def test_future_and_stale_windows_are_not_scored(prepared):
    session, detector = prepared
    window = session.scenario.windows[0]

    with pytest.raises(ValueError, match="future"):
        detector.score(
            window,
            as_of=window.end - timedelta(minutes=1),
        )

    with pytest.raises(ValueError, match="stale"):
        detector.score(
            window,
            as_of=window.end + timedelta(
                hours=detector.settings.max_reading_age_hours + 1
            ),
        )


def test_direction_is_separate_from_anomaly_score(prepared):
    session, detector = prepared
    original = session.scenario.windows[0]

    baseline = detector.baselines[
        (original.patient_id, original.start.hour // 4)
    ]

    changed = replace(
        original,
        resting_hr=baseline.hr_median + 20,
        steps=0,
    )

    result = detector.score(changed, as_of=changed.end)

    assert result.hr_above_baseline
    assert result.activity_below_baseline
    assert len(result.observed_changes) == 2


def test_scoring_does_not_update_baselines(prepared):
    session, detector = prepared
    before = dict(detector.baselines)

    for window in session.scenario.windows:
        detector.score(window, as_of=window.end)

    assert detector.baselines == before


def test_reference_cannot_be_reused_as_calibration(prepared):
    session, _ = prepared

    with pytest.raises(ValueError, match="share record IDs"):
        train_detector(session.reference, session.reference)