"""Personal baselines and Isolation Forest inference.

No Streamlit imports and no review creation.
All parameters are experimental synthetic-demo settings.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from math import log1p

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from config import DemoSettings, SETTINGS
from domain import (
    ConnectionStatus,
    WearableWindow,
    require_aware,
)


@dataclass(frozen=True)
class Baseline:
    patient_id: str
    slot: int
    hr_median: float
    hr_spread: float
    log_steps_median: float
    log_steps_spread: float
    sample_count: int


@dataclass(frozen=True)
class DetectionResult:
    window_id: str
    anomaly_score: float
    threshold: float
    is_anomalous: bool
    hr_deviation: float
    activity_deviation: float
    hr_above_baseline: bool
    activity_below_baseline: bool
    observed_changes: tuple[str, ...]


def slot_for(window: WearableWindow) -> int:
    """Fixtures use fixed UTC slots: 00, 04, 08, 12, 16, 20."""
    start = window.start.astimezone(timezone.utc)

    if (
        start.hour % 4 != 0
        or start.minute != 0
        or start.second != 0
        or start.microsecond != 0
    ):
        raise ValueError("Window must start on a four-hour UTC boundary.")

    return start.hour // 4


def require_measurements(
    window: WearableWindow,
    settings: DemoSettings,
) -> None:
    """Defensive input checks; invalid inputs must never be scored."""
    if window.connection != ConnectionStatus.CONNECTED:
        raise ValueError("Wearable is not connected.")

    if window.resting_hr is None or window.steps is None:
        raise ValueError("Wearable measurements are missing.")

    if (
        window.coverage_percent is None
        or window.coverage_percent < settings.min_coverage_percent
    ):
        raise ValueError("Wearable coverage is insufficient.")


def feature_vector(
    window: WearableWindow,
    baseline: Baseline,
) -> tuple[float, float]:
    return (
        (window.resting_hr - baseline.hr_median)
        / baseline.hr_spread,

        (log1p(window.steps) - baseline.log_steps_median)
        / baseline.log_steps_spread,
    )


def validate_dataset(
    windows: tuple[WearableWindow, ...],
    settings: DemoSettings,
) -> None:
    if not windows:
        raise ValueError("Dataset must not be empty.")

    ids = [window.id for window in windows]
    if len(ids) != len(set(ids)):
        raise ValueError("Dataset contains duplicate IDs.")

    keys = [
        (window.patient_id, window.start, window.end)
        for window in windows
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("Dataset contains duplicate patient windows.")

    for window in windows:
        require_measurements(window, settings)
        slot_for(window)


def build_baselines(
    reference: tuple[WearableWindow, ...],
    settings: DemoSettings,
) -> dict[tuple[str, int], Baseline]:
    frame = pd.DataFrame(
        [
            {
                "patient_id": window.patient_id,
                "slot": slot_for(window),
                "resting_hr": window.resting_hr,
                "log_steps": log1p(window.steps),
            }
            for window in reference
        ]
    )

    baselines = {}

    for (patient_id, slot), group in frame.groupby(
        ["patient_id", "slot"], sort=True
    ):
        if len(group) < settings.reference_days:
            raise ValueError(
                f"Insufficient reference data for {patient_id}, slot {slot}."
            )

        hr = group["resting_hr"].to_numpy(dtype=float)
        activity = group["log_steps"].to_numpy(dtype=float)

        hr_median = float(np.median(hr))
        activity_median = float(np.median(activity))

        hr_mad = float(np.median(np.abs(hr - hr_median)))
        activity_mad = float(
            np.median(np.abs(activity - activity_median))
        )

        key = (str(patient_id), int(slot))

        baselines[key] = Baseline(
            patient_id=str(patient_id),
            slot=int(slot),
            hr_median=hr_median,
            hr_spread=max(hr_mad, settings.min_hr_mad_bpm),
            log_steps_median=activity_median,
            log_steps_spread=max(
                activity_mad,
                settings.min_log_steps_mad,
            ),
            sample_count=len(group),
        )

    for patient_id in frame["patient_id"].unique():
        for slot in range(6):
            if (patient_id, slot) not in baselines:
                raise ValueError(
                    f"Missing baseline for {patient_id}, slot {slot}."
                )

    return baselines


def feature_matrix(
    windows: tuple[WearableWindow, ...],
    baselines: dict[tuple[str, int], Baseline],
) -> np.ndarray:
    rows = []

    for window in windows:
        key = (window.patient_id, slot_for(window))

        if key not in baselines:
            raise ValueError(f"No personal baseline for {key}.")

        rows.append(feature_vector(window, baselines[key]))

    matrix = np.asarray(rows, dtype=float)

    if not np.isfinite(matrix).all():
        raise ValueError("Features must be finite.")

    return matrix


@dataclass
class PersonalDetector:
    baselines: dict[tuple[str, int], Baseline]
    model: IsolationForest
    threshold: float
    settings: DemoSettings
    reference_count: int
    calibration_count: int

    def score(
        self,
        window: WearableWindow,
        *,
        as_of: datetime,
    ) -> DetectionResult:
        require_aware(as_of)
        require_measurements(window, self.settings)

        if window.end > as_of:
            raise ValueError("Cannot score an incomplete or future window.")

        age_hours = (as_of - window.end).total_seconds() / 3600

        if age_hours > self.settings.max_reading_age_hours:
            raise ValueError("Wearable window is stale.")

        key = (window.patient_id, slot_for(window))

        if key not in self.baselines:
            raise ValueError(f"No personal baseline for {key}.")

        baseline = self.baselines[key]
        hr_deviation, activity_deviation = feature_vector(
            window, baseline
        )

        features = np.asarray(
            [[hr_deviation, activity_deviation]],
            dtype=float,
        )

        score = float(-self.model.score_samples(features)[0])

        if not np.isfinite(score):
            raise ValueError("Model returned a non-finite score.")

        hr_above = hr_deviation > 0
        activity_below = activity_deviation < 0

        hr_relation = (
            "above" if hr_deviation > 0
            else "below" if hr_deviation < 0
            else "at"
        )
        activity_relation = (
            "above" if activity_deviation > 0
            else "below" if activity_deviation < 0
            else "at"
        )

        # Inverse-transform the log-space baseline for readable display.
        baseline_steps = float(np.expm1(baseline.log_steps_median))

        observations = (
            (
                f"Resting HR {window.resting_hr:.1f} bpm is "
                f"{hr_relation} baseline {baseline.hr_median:.1f} bpm."
            ),
            (
                f"Activity {window.steps} steps is "
                f"{activity_relation} baseline approximately "
                f"{baseline_steps:.0f} steps for this time slot."
            ),
        )

        return DetectionResult(
            window_id=window.id,
            anomaly_score=score,
            threshold=self.threshold,
            is_anomalous=score > self.threshold,
            hr_deviation=float(hr_deviation),
            activity_deviation=float(activity_deviation),
            hr_above_baseline=hr_above,
            activity_below_baseline=activity_below,
            observed_changes=observations,
        )


def train_detector(
    reference: tuple[WearableWindow, ...],
    calibration: tuple[WearableWindow, ...],
    settings: DemoSettings = SETTINGS,
) -> PersonalDetector:
    """Fit on reference data, then calibrate using separate stable data."""
    if settings.window_hours != 4:
        raise ValueError("Detector expects four-hour windows.")

    if (
        settings.min_hr_mad_bpm <= 0
        or settings.min_log_steps_mad <= 0
    ):
        raise ValueError("Baseline spread floors must be positive.")

    if not 0 < settings.threshold_percentile < 100:
        raise ValueError("Threshold percentile must be between 0 and 100.")

    validate_dataset(reference, settings)
    validate_dataset(calibration, settings)

    reference_ids = {window.id for window in reference}
    calibration_ids = {window.id for window in calibration}

    if reference_ids & calibration_ids:
        raise ValueError("Reference and calibration share record IDs.")

    if max(window.end for window in reference) > min(
        window.start for window in calibration
    ):
        raise ValueError("Reference and calibration periods overlap.")

    reference_patients = {window.patient_id for window in reference}
    calibration_patients = {window.patient_id for window in calibration}

    if reference_patients != calibration_patients:
        raise ValueError("Calibration must cover the reference patients.")

    # Require calibration observations for every patient/time slot.
    for patient_id in reference_patients:
        for slot in range(6):
            count = sum(
                window.patient_id == patient_id
                and slot_for(window) == slot
                for window in calibration
            )
            if count < settings.calibration_days:
                raise ValueError(
                    f"Insufficient calibration data for {patient_id}, "
                    f"slot {slot}."
                )

    baselines = build_baselines(reference, settings)
    reference_features = feature_matrix(reference, baselines)
    calibration_features = feature_matrix(calibration, baselines)

    model = IsolationForest(
        n_estimators=settings.n_estimators,
        random_state=settings.random_seed,
    )
    model.fit(reference_features)

    calibration_scores = -model.score_samples(calibration_features)

    threshold = float(
        np.percentile(
            calibration_scores,
            settings.threshold_percentile,
        )
    )

    if not np.isfinite(threshold):
        raise ValueError("Calibration returned a non-finite threshold.")

    return PersonalDetector(
        baselines=baselines,
        model=model,
        threshold=threshold,
        settings=settings,
        reference_count=len(reference),
        calibration_count=len(calibration),
    )