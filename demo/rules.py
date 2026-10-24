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


def concern_reasons(checkin: CheckIn) -> tuple[str, ...]:
    """Temperature is displayed, but does not trigger a threshold rule."""
    reasons = []

    if checkin.feeling == Feeling.UNWELL:
        reasons.append("Patient reports feeling unwell.")
    elif checkin.feeling == Feeling.WORSE:
        reasons.append("Patient reports feeling worse than usual.")

    if checkin.symptoms:
        reasons.append(
            "Reported symptoms: " + ", ".join(checkin.symptoms) + "."
        )

    return tuple(reasons)


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