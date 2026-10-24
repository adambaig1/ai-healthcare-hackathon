"""Replay wearable windows using the real model and review rules."""

from data import create_session
from monitoring import initialise_engine, assess_window


def main():
    session = create_session("sustained_change")
    engine = initialise_engine(session)

    if engine.detector is None:
        raise RuntimeError(engine.startup_error)

    for window in session.scenario.windows:
        assess_window(
            session.state,
            engine,
            window,
            as_of=window.end,
        )

    for patient in session.state.patients.values():
        reviews = [
            item for item in session.state.reviews.values()
            if item.patient_id == patient.id
        ]

        print(f"\n{patient.name}: {len(reviews)} review item(s)")

        for review in reviews:
            print("Created:", review.created_at.isoformat())
            print("Status:", review.status.value)
            print("Evidence records:", len(review.evidence_ids))

    print("\nAssessments:", len(session.state.assessments))


if __name__ == "__main__":
    main()