"""Patient-concern and review-transition rules.

No Streamlit imports, storage writes or AI dependencies.
"""

from dataclasses import replace
from datetime import datetime

from domain import (
    ActionType,
    CheckIn,
    Feeling,
    ReviewItem,
    ReviewStatus,
)

from typing import Optional
from domain import CheckIn, Assessment, Feeling, Symptom

def evaluate_clinical_score(
    checkin: Optional[CheckIn] = None, 
    assessment: Optional[Assessment] = None
) -> tuple[int, list[str]]:
    """Calculates a NEWS2-style score. >= 4 triggers a nurse review."""
    score = 0
    reasons = []

    # 1. AI Anomaly (+2 points)
    if assessment and getattr(assessment, 'is_anomalous', False):
        score += 2
        reasons.append("+2: Wearable data indicates sustained abnormal trends (AI flagged)")

    if checkin:
        # 2. Feeling Score (3 = +1, 4 = +2, 5 = +3)
# ... inside demo/rules.py ...
        
        # 2. Feeling Score (3 = +1, 4 = +2, 5 = +4)
        if checkin.feeling == Feeling.NOT_WELL:
            score += 1
            reasons.append("+1: Patient reported feeling 'Not Well' (Score: 3)")
        elif checkin.feeling == Feeling.VERY_UNWELL:
            score += 2
            reasons.append("+2: Patient reported feeling 'Very Unwell' (Score: 4)")
        elif checkin.feeling == Feeling.EXTREMELY_UNWELL:
            score += 4  # <--- CHANGED FROM 3 TO 4
            reasons.append("+4: Patient reported feeling 'Extremely Unwell' (SOS Trigger)")

        # 3. Symptoms (+2 points if any high-risk symptom is present)
        if checkin.symptoms:
            score += 2
            symptom_names = ", ".join([Symptom(s).name.replace("_", " ").title() for s in checkin.symptoms])
            reasons.append(f"+2: High-risk symptoms reported ({symptom_names})")

        # 4. Temperature (+3 points if > 38.0)
        if checkin.temperature_c is not None and checkin.temperature_c > 38.0:
            score += 3
            reasons.append(f"+3: Temperature meets escalation criteria ({checkin.temperature_c}°C)")

    return score, tuple(reasons)


def mark_review_seen(
    review: ReviewItem,
    timestamp: datetime,
) -> ReviewItem:
    if review.status != ReviewStatus.NEW:
        raise ValueError("Only a new review can be marked seen.")

    return replace(
        review,
        status=ReviewStatus.SEEN,
        seen_at=timestamp,
        updated_at=timestamp,
    )


def record_review_action(
    review: ReviewItem,
    timestamp: datetime,
    action_type: ActionType,
    note: str,
) -> ReviewItem:
    if review.status != ReviewStatus.SEEN:
        raise ValueError("Mark the review seen before recording an action.")

    note = note.strip()
    if not note:
        raise ValueError("Enter an action note.")

    return replace(
        review,
        status=ReviewStatus.ACTION_RECORDED,
        action_recorded_at=timestamp,
        action_type=action_type,
        action_note=note,
        updated_at=timestamp,
    )

from config import DemoSettings, SETTINGS
from domain import (
    ConnectionStatus,
    DataQuality,
    WearableWindow,
    require_aware,
)


def window_quality(
    window: WearableWindow,
    *,
    as_of: datetime,
    settings: DemoSettings = SETTINGS,
) -> DataQuality:
    require_aware(as_of)

    if window.end > as_of:
        raise ValueError("Cannot assess an incomplete or future window.")

    if window.connection != ConnectionStatus.CONNECTED:
        return DataQuality.DISCONNECTED

    if window.resting_hr is None or window.steps is None:
        return DataQuality.MISSING

    if (
        window.coverage_percent is None
        or window.coverage_percent < settings.min_coverage_percent
    ):
        return DataQuality.INSUFFICIENT_COVERAGE

    age_hours = (as_of - window.end).total_seconds() / 3600

    if age_hours > settings.max_reading_age_hours:
        return DataQuality.STALE

    return DataQuality.AVAILABLE