"""Application operations for check-ins and nurse review actions."""

from dataclasses import replace

from domain import (
    ActionType,
    Actor,
    AppState,
    AuditEvent,
    CheckIn,
    Feeling,
    ReviewItem,
    new_id,
)
from rules import (
    evaluate_clinical_score,
    mark_review_seen,
    record_review_action,
)


def command_key(operation: str, command_id: str) -> str:
    """A repeated command must have the same ID."""
    if not command_id.strip():
        raise ValueError("A command ID is required.")
    return f"{operation}:{command_id}"


def get_open_review(
    state: AppState,
    patient_id: str,
) -> ReviewItem | None:
    reviews = [
        review
        for review in state.reviews.values()
        if review.patient_id == patient_id and review.is_open
    ]

    if len(reviews) > 1:
        raise ValueError("Patient has multiple open review items.")

    return reviews[0] if reviews else None

def submit_checkin(
    state: AppState,
    *,
    command_id: str,
    patient_id: str,
    feeling: int,
    symptoms: tuple[str, ...] = (),
    temperature_c: float | None = None,
    checkin_id: str | None = None,
) -> None:
    key = command_key("submit_checkin", command_id)

    # Safe to retry an already completed command.
    if key in state.processed_command_ids:
        return

    if patient_id not in state.patients:
        raise ValueError("Unknown patient.")

    feeling_enum = Feeling(feeling)

    # Remove whitespace, blanks and repeated symptom selections.
    cleaned_symptoms = tuple(
        dict.fromkeys(
            symptom.strip()
            for symptom in symptoms
            if symptom.strip()
        )
    )

    record_id = checkin_id or new_id()

    if record_id in state.checkins:
        raise ValueError("Check-in ID already exists.")

    checkin = CheckIn(
        id=record_id,
        patient_id=patient_id,
        timestamp=state.simulated_time,
        feeling=feeling_enum,
        symptoms=cleaned_symptoms,
        temperature_c=temperature_c,
    )

    # In demo/services.py, inside submit_checkin()

    # Find the most recent assessment for this patient
    latest_assessment = next(
        (
            item for item in sorted(
                state.assessments.values(), 
                key=lambda x: x.timestamp, 
                reverse=True
            )
            if item.patient_id == patient_id
        ),
        None
    )

    # Pass both to the rules engine to get the combined NEWS2 score
    score, reasons = evaluate_clinical_score(
        checkin=checkin, 
        assessment=latest_assessment
    )

    # Prepare and validate all records before changing state.
    events = [
        AuditEvent(
            timestamp=state.simulated_time,
            actor=Actor.PATIENT,
            action="checkin_submitted",
            record_id=checkin.id,
            details=f"Feeling Score: {checkin.feeling.value}.",
        )
    ]

    review = None

    # THRESHOLD LOGIC: Score must be >= 4 to trigger the ReviewItem
    if score >= 4:
        existing = get_open_review(state, patient_id)

        if existing is None:
            review = ReviewItem(
                patient_id=patient_id,
                reasons=reasons,
                evidence_ids=(checkin.id,),
                created_at=state.simulated_time,
                updated_at=state.simulated_time,
            )
            audit_action = "review_created"
        else:
            review = replace(
                existing,
                reasons=tuple(
                    dict.fromkeys((*existing.reasons, *reasons))
                ),
                evidence_ids=(*existing.evidence_ids, checkin.id),
                updated_at=state.simulated_time,
            )
            audit_action = "review_evidence_added"

        events.append(
            AuditEvent(
                timestamp=state.simulated_time,
                actor=Actor.SYSTEM,
                action=audit_action,
                record_id=review.id,
                details=f"Supporting check-in: {checkin.id} (Score: {score}).",
            )
        )

    state.checkins[checkin.id] = checkin

    if review is not None:
        state.reviews[review.id] = review

    state.audit_events.extend(events)
    state.processed_command_ids.add(key)

def mark_seen(
    state: AppState,
    *,
    command_id: str,
    review_id: str,
) -> None:
    key = command_key("mark_seen", command_id)

    if key in state.processed_command_ids:
        return

    if review_id not in state.reviews:
        raise ValueError("Unknown review.")

    updated = mark_review_seen(
        state.reviews[review_id],
        state.simulated_time,
    )

    event = AuditEvent(
        timestamp=state.simulated_time,
        actor=Actor.NURSE,
        action="review_seen",
        record_id=review_id,
    )

    state.reviews[review_id] = updated
    state.audit_events.append(event)
    state.processed_command_ids.add(key)


def record_action(
    state: AppState,
    *,
    command_id: str,
    review_id: str,
    action_type: ActionType,
    note: str,
) -> None:
    key = command_key("record_action", command_id)

    if key in state.processed_command_ids:
        return

    if review_id not in state.reviews:
        raise ValueError("Unknown review.")

    updated = record_review_action(
        state.reviews[review_id],
        state.simulated_time,
        ActionType(action_type),
        note,
    )

    event = AuditEvent(
        timestamp=state.simulated_time,
        actor=Actor.NURSE,
        action="review_action_recorded",
        record_id=review_id,
        details=f"{updated.action_type.value}: {updated.action_note}",
    )

    state.reviews[review_id] = updated
    state.audit_events.append(event)
    state.processed_command_ids.add(key)