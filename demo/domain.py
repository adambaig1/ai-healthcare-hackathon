"""Domain records for the Oncology Watch synthetic demonstration."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from math import isfinite
from uuid import uuid4


def new_id() -> str:
    """Create an ID when a record is first created."""
    return str(uuid4())


def require_aware(value: datetime) -> None:
    """Reject timestamps without an explicit timezone."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamps must be timezone-aware.")


def require_finite(value: float | None, name: str) -> None:
    """Missing values must be None, not NaN or infinity."""
    if value is not None and not isfinite(value):
        raise ValueError(f"{name} must be finite or None.")


class Feeling(int, Enum):
    WELL = 1
    MOSTLY_WELL = 2
    NOT_WELL = 3
    VERY_UNWELL = 4
    EXTREMELY_UNWELL = 5

class Symptom(str, Enum):
    FEVERISH = "feeling_feverish_hot_or_unusually_cold"
    CHILLS = "chills_or_shivering"
    FATIGUE = "unusual_tiredness_or_weakness"
    COUGH = "new_or_worsening_cough"
    BREATHLESSNESS = "new_or_worsening_breathlessness"
    SORE_THROAT = "sore_throat_or_mouth_sores"
    NAUSEA = "feeling_sick_nausea"
    VOMITING = "being_sick_vomiting"
    DIARRHOEA = "diarrhoea"
    URINE_PAIN = "pain_or_burning_when_passing_urine"
    LESS_URINE = "passing_less_urine_than_usual"
    LINE_REDNESS = "redness_swelling_pain_or_discharge_around_wound_or_line"
    DIZZINESS = "dizziness_or_feeling_faint"
    NEW_PAIN = "new_or_worsening_pain"


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"


class DataQuality(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    DISCONNECTED = "disconnected"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    STALE = "stale"


class AnalysisStatus(str, Enum):
    NOT_RUN = "not_run"
    SCORED = "scored"
    UNAVAILABLE = "unavailable"


class ReviewStatus(str, Enum):
    NEW = "new"
    SEEN = "seen"
    ACTION_RECORDED = "action_recorded"


class ActionType(str, Enum):
    CONTACT_ATTEMPTED = "contact_attempted"
    CONTACT_COMPLETED = "contact_completed"
    REFERRED_FOR_REVIEW = "referred_for_review"


class Actor(str, Enum):
    SYSTEM = "system"
    PATIENT = "patient"
    NURSE = "nurse"


@dataclass(frozen=True)
class Patient:
    id: str
    name: str
    baseline_id: str


@dataclass(frozen=True)
class WearableWindow:
    patient_id: str
    start: datetime
    end: datetime
    resting_hr: float | None
    steps: int | None
    coverage_percent: float | None
    connection: ConnectionStatus
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        require_aware(self.start)
        require_aware(self.end)

        if self.end - self.start != timedelta(hours=4):
            raise ValueError("Wearable windows must cover exactly four hours.")

        require_finite(self.resting_hr, "resting_hr")
        require_finite(self.steps, "steps")
        require_finite(self.coverage_percent, "coverage_percent")

        if self.resting_hr is not None and self.resting_hr <= 0:
            raise ValueError("resting_hr must be positive or None.")

        if self.steps is not None:
            if type(self.steps) is not int or self.steps < 0:
                raise ValueError("steps must be a non-negative integer or None.")

        if self.coverage_percent is not None:
            if not 0 <= self.coverage_percent <= 100:
                raise ValueError("coverage_percent must be between 0 and 100.")

@dataclass(frozen=True)
class CheckIn:
    patient_id: str
    timestamp: datetime
    feeling: Feeling
    symptoms: tuple[Symptom, ...] = ()  # Updated to use the new Enum
    temperature_c: float | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        require_aware(self.timestamp)
        require_finite(self.temperature_c, "temperature_c")


@dataclass(frozen=True)
class Assessment:
    patient_id: str
    window_id: str
    timestamp: datetime
    data_quality: DataQuality
    analysis_status: AnalysisStatus
    anomaly_score: float | None = None
    is_anomalous: bool | None = None
    persistent_change: bool = False
    observed_changes: tuple[str, ...] = ()
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        require_aware(self.timestamp)
        require_finite(self.anomaly_score, "anomaly_score")

        if self.analysis_status == AnalysisStatus.SCORED:
            if self.data_quality != DataQuality.AVAILABLE:
                raise ValueError("Only usable data can receive a score.")

            if self.anomaly_score is None or self.is_anomalous is None:
                raise ValueError("Scored assessments require a score and result.")
        else:
            if self.anomaly_score is not None or self.is_anomalous is not None:
                raise ValueError("Unscored assessments must not contain AI results.")

        if self.persistent_change and not (
            self.analysis_status == AnalysisStatus.SCORED
            and self.is_anomalous is True
        ):
            raise ValueError("Persistent change requires an anomalous scored window.")


@dataclass(frozen=True)
class ReviewItem:
    patient_id: str
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    status: ReviewStatus = ReviewStatus.NEW
    seen_at: datetime | None = None
    action_recorded_at: datetime | None = None
    action_type: ActionType | None = None
    action_note: str | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        require_aware(self.created_at)
        require_aware(self.updated_at)

        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at.")

        if not self.reasons or any(not reason.strip() for reason in self.reasons):
            raise ValueError("Reviews require non-empty reasons.")

        if not self.evidence_ids:
            raise ValueError("Reviews require supporting evidence IDs.")

        if self.seen_at is not None:
            require_aware(self.seen_at)
            if not self.created_at <= self.seen_at <= self.updated_at:
                raise ValueError("seen_at must fall within the review timeline.")

        if self.status == ReviewStatus.NEW and self.seen_at is not None:
            raise ValueError("A new review cannot already be marked seen.")

        if self.status != ReviewStatus.NEW and self.seen_at is None:
            raise ValueError("Seen and action-recorded reviews require seen_at.")

        if self.status == ReviewStatus.ACTION_RECORDED:
            if self.action_type is None:
                raise ValueError("Recording an action requires an action type.")

            if not self.action_note or not self.action_note.strip():
                raise ValueError("Recording an action requires a note.")

            if self.action_recorded_at is None:
                raise ValueError("Recording an action requires a timestamp.")

            require_aware(self.action_recorded_at)

            if not self.seen_at <= self.action_recorded_at <= self.updated_at:
                raise ValueError("Action timestamp must follow the seen timestamp.")
        elif any(
            value is not None
            for value in (
                self.action_recorded_at,
                self.action_type,
                self.action_note,
            )
        ):
            raise ValueError("Action fields belong to action-recorded reviews.")

    @property
    def is_open(self) -> bool:
        """Task completion does not imply clinical resolution."""
        return self.status in (ReviewStatus.NEW, ReviewStatus.SEEN)


@dataclass(frozen=True)
class AuditEvent:
    timestamp: datetime
    actor: Actor
    action: str
    record_id: str
    details: str = ""
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        require_aware(self.timestamp)

@dataclass
class TrendState:
    """Per-patient tracking for a continuous wearable-change episode."""

    last_window_end: datetime | None = None
    consecutive_count: int = 0
    recent_assessment_ids: tuple[str, ...] = ()

    # Prevent repeated tasks after an action is recorded while the
    # same uninterrupted trend continues.
    episode_notified: bool = False

@dataclass
class AppState:
    """Mutable session container; individual records remain immutable."""

    scenario_id: str
    simulated_time: datetime

    patients: dict[str, Patient] = field(default_factory=dict)
    windows: dict[str, WearableWindow] = field(default_factory=dict)
    checkins: dict[str, CheckIn] = field(default_factory=dict)
    assessments: dict[str, Assessment] = field(default_factory=dict)
    reviews: dict[str, ReviewItem] = field(default_factory=dict)
    audit_events: list[AuditEvent] = field(default_factory=list)
    trends: dict[str, TrendState] = field(default_factory=dict)

    # Used later to make application commands safe to repeat.
    processed_window_ids: set[str] = field(default_factory=set)
    processed_command_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        require_aware(self.simulated_time)