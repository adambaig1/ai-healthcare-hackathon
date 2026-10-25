"""Coordinate wearable assessment, persistence and review updates."""

from dataclasses import dataclass, replace
from datetime import datetime

from config import DemoSettings, SETTINGS
from data import DemoSession
from detector import PersonalDetector, train_detector
from domain import (
    Actor,
    AnalysisStatus,
    AppState,
    Assessment,
    AuditEvent,
    DataQuality,
    ReviewItem,
    TrendState,
    WearableWindow,
    require_aware,
)
from rules import window_quality
from services import get_open_review


@dataclass
class AnalysisEngine:
    detector: PersonalDetector | None
    settings: DemoSettings = SETTINGS
    startup_error: str | None = None


def initialise_engine(session: DemoSession) -> AnalysisEngine:
    """Training failure must not prevent patient check-ins."""
    try:
        detector = train_detector(
            session.reference,
            session.calibration,
        )
    except Exception as error:
        # Deliberate fault boundary around model preparation only.
        return AnalysisEngine(
            detector=None,
            startup_error=f"Model preparation failed: {type(error).__name__}",
        )

    return AnalysisEngine(
        detector=detector,
        settings=detector.settings,
    )


def update_trend_review(
    state: AppState,
    trend: TrendState,
    assessment: Assessment,
) -> bool:
    """Return whether this trend episode has been notified."""
    existing = get_open_review(state, assessment.patient_id)

    # The previous task was actioned, but the same trend continues.
    # Do not create another task for every subsequent window.
    if existing is None and trend.episode_notified:
        return True

    reasons = (
        "Persistent wearable pattern: higher resting heart rate "
        "and lower activity relative to personal baselines.",
    )

    if existing is None:
        review = ReviewItem(
            patient_id=assessment.patient_id,
            reasons=reasons,
            evidence_ids=trend.recent_assessment_ids,
            created_at=assessment.timestamp,
            updated_at=assessment.timestamp,
        )
        action = "review_created"
    else:
        review = replace(
            existing,
            reasons=tuple(dict.fromkeys((*existing.reasons, *reasons))),
            evidence_ids=tuple(
                dict.fromkeys(
                    (
                        *existing.evidence_ids,
                        *trend.recent_assessment_ids,
                    )
                )
            ),
            updated_at=assessment.timestamp,
        )
        action = "review_evidence_added"

    state.reviews[review.id] = review

    state.audit_events.append(
        AuditEvent(
            timestamp=assessment.timestamp,
            actor=Actor.SYSTEM,
            action=action,
            record_id=review.id,
            details=f"Wearable assessment: {assessment.id}.",
        )
    )

    return True


def assess_window(
    state: AppState,
    engine: AnalysisEngine,
    window: WearableWindow,
    *,
    as_of: datetime,
) -> None:
    """Process one window once, in chronological order."""
    require_aware(as_of)

    if window.id in state.processed_window_ids:
        return

    if window.patient_id not in state.patients:
        raise ValueError("Unknown patient.")

    if as_of < state.simulated_time:
        raise ValueError("Assessment cannot move simulated time backwards.")

    if window.end > as_of:
        raise ValueError("Cannot process a future window.")

    if any(
        other.id != window.id
        and other.patient_id == window.patient_id
        and other.start == window.start
        and other.end == window.end
        for other in state.windows.values()
    ):
        raise ValueError("Duplicate patient/time window.")

    previous = state.trends.get(window.patient_id, TrendState())

    if (
        previous.last_window_end is not None
        and window.start < previous.last_window_end
    ):
        raise ValueError("Patient windows must be processed in order.")

    quality = window_quality(
        window,
        as_of=as_of,
        settings=engine.settings,
    )

    result = None
    analysis_status = AnalysisStatus.NOT_RUN
    observations = (f"Wearable data unavailable: {quality.value}.",)

    if quality == DataQuality.AVAILABLE:
        if engine.detector is None:
            analysis_status = AnalysisStatus.UNAVAILABLE
            observations = ("AI analysis unavailable.",)
        else:
            try:
                result = engine.detector.score(window, as_of=as_of)
            except Exception:
                # Deliberate inference fault boundary.
                # Do not turn a model failure into a normal score.
                analysis_status = AnalysisStatus.UNAVAILABLE
                observations = ("AI analysis unavailable.",)
            else:
                analysis_status = AnalysisStatus.SCORED
                observations = result.observed_changes

    qualifies = (
        result is not None
        and result.is_anomalous
        and result.hr_above_baseline
        and result.activity_below_baseline
    )

    adjacent = previous.last_window_end == window.start

    trend = TrendState(
        last_window_end=window.end,
        episode_notified=previous.episode_notified,
    )

    if qualifies:
        trend.consecutive_count = (
            previous.consecutive_count + 1 if adjacent else 1
        )
    elif analysis_status == AnalysisStatus.SCORED:
        # A valid non-qualifying result ends the previous episode.
        trend.episode_notified = False

    persistent = (
        qualifies
        and trend.consecutive_count
        >= engine.settings.consecutive_windows
    )

    assessment = Assessment(
        patient_id=window.patient_id,
        window_id=window.id,
        timestamp=as_of,
        data_quality=quality,
        analysis_status=analysis_status,
        anomaly_score=(
            result.anomaly_score if result is not None else None
        ),
        is_anomalous=(
            result.is_anomalous if result is not None else None
        ),
        persistent_change=persistent,
        observed_changes=observations,
    )

    if qualifies:
        previous_ids = previous.recent_assessment_ids if adjacent else ()
        trend.recent_assessment_ids = (
            *previous_ids,
            assessment.id,
        )[-engine.settings.consecutive_windows:]



    state.windows[window.id] = window
    state.assessments[assessment.id] = assessment
    state.trends[window.patient_id] = trend

    state.audit_events.append(
        AuditEvent(
            timestamp=as_of,
            actor=Actor.SYSTEM,
            action="window_assessed",
            record_id=assessment.id,
            details=(
                f"Data quality: {quality.value}; "
                f"analysis: {analysis_status.value}."
            ),
        )
    )

    state.processed_window_ids.add(window.id)
    state.simulated_time = as_of


def monitoring_summary(
    state: AppState,
    patient_id: str,
    settings: DemoSettings = SETTINGS,
) -> dict[str, str]:
    """Describe current availability without hiding existing reviews."""
    windows = [
        window
        for window in state.windows.values()
        if window.patient_id == patient_id
        and window.end <= state.simulated_time
    ]

    last_usable = max(
        (
            window.end
            for window in windows
            if window_quality(
                window,
                as_of=window.end,
                settings=settings,
            ) == DataQuality.AVAILABLE
        ),
        default=None,
    )

    last_usable_text = (
        last_usable.strftime("%d %b %Y, %H:%M %Z")
        if last_usable is not None
        else "None"
    )

    if not windows:
        return {
            "status": "Monitoring unavailable",
            "detail": "No completed readings.",
            "last_usable": last_usable_text,
        }

    latest = max(windows, key=lambda window: window.end)

    quality = window_quality(
        latest,
        as_of=state.simulated_time,
        settings=settings,
    )

    if quality != DataQuality.AVAILABLE:
        return {
            "status": "Monitoring unavailable",
            "detail": quality.value.replace("_", " ").capitalize(),
            "last_usable": last_usable_text,
        }

    assessment = next(
        (
            item
            for item in state.assessments.values()
            if item.window_id == latest.id
        ),
        None,
    )

    if assessment is None:
        status = "Analysis pending"
    elif assessment.analysis_status == AnalysisStatus.UNAVAILABLE:
        status = "AI analysis unavailable"
    elif assessment.analysis_status == AnalysisStatus.SCORED:
        status = "Monitoring available"
    else:
        status = "Analysis pending"

    return {
        "status": status,
        "detail": "Latest measurements are available.",
        "last_usable": last_usable_text,
    }