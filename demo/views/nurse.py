"""Nurse dashboard: monitoring, evidence, reviews and audit history."""

import streamlit as st

from domain import ActionType, AppState, ReviewStatus, Symptom, new_id
from monitoring import monitoring_summary
from services import get_open_review, mark_seen, record_action
from views.charts import build_chart_data, build_trend_figure


STATUS_LABELS = {
    ReviewStatus.NEW: "New",
    ReviewStatus.SEEN: "Seen",
    ReviewStatus.ACTION_RECORDED: "Action recorded",
}

ACTION_LABELS = {
    ActionType.CONTACT_ATTEMPTED: "Contact attempted",
    ActionType.CONTACT_COMPLETED: "Contact completed",
    ActionType.REFERRED_FOR_REVIEW: "Referred for review",
}

STATUS_PRIORITY = {
    ReviewStatus.NEW: 0,
    ReviewStatus.SEEN: 1,
    ReviewStatus.ACTION_RECORDED: 2,
}


def format_time(timestamp) -> str:
    return timestamp.strftime("%d %b %Y, %H:%M UTC")


def patient_priority(state: AppState, patient_id: str) -> tuple:
    review = get_open_review(state, patient_id)

    return (
        STATUS_PRIORITY[review.status] if review else 3,
        state.patients[patient_id].name,
    )


def render_patient_list(state: AppState) -> list[str]:
    patient_ids = sorted(
        state.patients,
        key=lambda patient_id: patient_priority(state, patient_id),
    )

    new_count = sum(
        review.status == ReviewStatus.NEW
        for review in state.reviews.values()
    )
    seen_count = sum(
        review.status == ReviewStatus.SEEN
        for review in state.reviews.values()
    )
    unavailable_count = sum(
        monitoring_summary(state, patient_id)["status"]
        == "Monitoring unavailable"
        for patient_id in patient_ids
    )

    first, second, third = st.columns(3)
    first.metric("New reviews", new_count)
    second.metric("Seen — action pending", seen_count)
    third.metric("Monitoring unavailable", unavailable_count)

    rows = []

    for patient_id in patient_ids:
        patient = state.patients[patient_id]
        review = get_open_review(state, patient_id)
        monitoring = monitoring_summary(state, patient_id)

        rows.append(
            {
                "Patient": patient.name,
                "Status": (
                    "EMERGENCY (SOS)" if review and review.status == ReviewStatus.NEW and any("Extremely Unwell" in r for r in review.reasons)
                    else "FLAGGED (Review Needed)" if review and review.status == ReviewStatus.NEW 
                    else "Under Review" if review and review.status == ReviewStatus.SEEN
                    else "Stable"
                ),
                "Monitoring": monitoring["status"],
                "Last usable measurement": monitoring["last_usable"],
            }
        )

    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption(
        "Ordered by review workflow status, not clinical severity. "
        "No open review does not mean a patient is well."
    )

    return patient_ids


def render_checkin(state: AppState, patient_id: str) -> None:
    checkins = [
        checkin
        for checkin in state.checkins.values()
        if checkin.patient_id == patient_id
    ]

    st.subheader("Latest patient report")

    if not checkins:
        st.info("No patient check-in submitted.")
        return

    latest = checkins[-1]

    st.write(f"**Feeling Score:** {latest.feeling.value}")
    st.write(
        "**Symptoms:** "
        + (", ".join([Symptom(s).name.replace("_", " ").title() for s in latest.symptoms]) or "None selected")
    )
    st.write(
        "**Temperature:** "
        + (
            f"{latest.temperature_c:g} °C"
            if latest.temperature_c is not None
            else "Not provided"
        )
    )
    st.caption("Submitted: " + format_time(latest.timestamp))


def render_evidence(state: AppState, review) -> None:
    with st.expander(
        f"Supporting observations ({len(review.evidence_ids)})"
    ):
        for evidence_id in review.evidence_ids:
            checkin = state.checkins.get(evidence_id)
            assessment = state.assessments.get(evidence_id)

            if checkin is not None:
                st.markdown("**Patient check-in**")
                st.caption(format_time(checkin.timestamp))
                st.write(f"Feeling Score: {checkin.feeling.value}")
                st.write(
                    "Symptoms: "
                    + (", ".join([Symptom(s).name.replace("_", " ").title() for s in checkin.symptoms]) or "None selected")
                )

                if checkin.temperature_c is not None:
                    st.write(f"Temperature: {checkin.temperature_c:g} °C")

            elif assessment is not None:
                st.markdown("**Wearable assessment**")
                st.caption("Assessed: " + format_time(assessment.timestamp))

                window = state.windows.get(assessment.window_id)

                if window is not None:
                    st.caption(
                        "Measurement window: "
                        + format_time(window.start)
                        + " → "
                        + format_time(window.end)
                    )

                for observation in assessment.observed_changes:
                    st.write(observation)

                if assessment.anomaly_score is not None:
                    st.caption(
                        f"Historical unusualness score: "
                        f"{assessment.anomaly_score:.4f}. "
                        "Not a probability or severity score."
                    )

            else:
                st.warning("Supporting record is unavailable.")

            st.divider()


def render_reviews(state: AppState, patient_id: str) -> None:
    st.subheader("Review tasks")

    reviews = [
        review
        for review in state.reviews.values()
        if review.patient_id == patient_id
    ]

    # Reverse insertion order first, then stable-sort by workflow status.
    reviews = sorted(
        reversed(reviews),
        key=lambda review: STATUS_PRIORITY[review.status],
    )

    if not reviews:
        st.info("No review tasks for this patient.")
        return

    for review in reviews:
        
        # Traffic light logic for the UI container
        if review.status == ReviewStatus.NEW:
            if any("Extremely Unwell" in r for r in review.reasons):
                header = "EMERGENCY: Patient Triggered SOS"
            else:
                header = "URGENT: Patient Flagged for Review"
        elif review.status == ReviewStatus.SEEN:
            header = "Review in Progress"
        else:
            header = "Action Recorded"

        with st.container(border=True):
            st.markdown(f"### {header}")
            st.caption(
                "Task Created: " + format_time(review.created_at) + 
                " · Last Updated: " + format_time(review.updated_at)
            )

            st.markdown(r"#### Clinical Score Breakdown (NEWS2 Threshold $\ge$ 4)")
            
            for reason in review.reasons:
                st.write(f"• **{reason}**")

            if (
                review.seen_at is not None
                and review.updated_at > review.seen_at
                and review.status == ReviewStatus.SEEN
            ):
                st.info("New evidence has arrived since this review was marked seen.")

            render_evidence(state, review)

            if review.status == ReviewStatus.NEW:
                if st.button(
                    "Mark seen",
                    key=f"seen_{review.id}",
                ):
                    mark_seen(
                        state,
                        command_id=new_id(),
                        review_id=review.id,
                    )
                    st.rerun()

            elif review.status == ReviewStatus.SEEN:
                with st.form(f"action_form_{review.id}"):
                    action_type = st.selectbox(
                        "Action type",
                        options=list(ActionType),
                        index=None,
                        placeholder="Choose an action",
                        format_func=lambda value: ACTION_LABELS[value],
                        key=f"action_type_{review.id}",
                    )

                    note = st.text_area(
                        "Action note",
                        key=f"action_note_{review.id}",
                        placeholder="Describe the action taken in this demo.",
                    )

                    submitted = st.form_submit_button(
                        "Record action",
                        key=f"record_action_{review.id}",
                    )

                if submitted:
                    if action_type is None:
                        st.error("Choose an action type.")
                    else:
                        try:
                            record_action(
                                state,
                                command_id=new_id(),
                                review_id=review.id,
                                action_type=action_type,
                                note=note,
                            )
                        except ValueError as error:
                            st.error(str(error))
                        else:
                            st.rerun()

            else:
                st.write(
                    "**Action:** " + ACTION_LABELS[review.action_type]
                )
                st.write(review.action_note)
                st.caption(
                    "Recorded: " + format_time(review.action_recorded_at)
                )
                st.caption(
                    "This completes the demo review task. "
                    "It does not establish clinical resolution."
                )


def render_audit(state: AppState, patient_id: str) -> None:
    relevant_ids = {
        item.id
        for collection in (
            state.checkins.values(),
            state.assessments.values(),
            state.reviews.values(),
        )
        for item in collection
        if item.patient_id == patient_id
    }

    rows = [
        {
            "Time — UTC": format_time(event.timestamp),
            "Actor": event.actor.value,
            "Action": event.action.replace("_", " "),
            "Details": event.details,
            "Record ID": event.record_id,
        }
        for event in state.audit_events
        if event.record_id in relevant_ids
    ]

    with st.expander("Audit history"):
        if rows:
            st.dataframe(rows, hide_index=True, width="stretch")
            st.caption(
                "Events are shown in recorded order. Equal timestamps "
                "are possible when the simulated clock has not advanced."
            )
        else:
            st.write("No recorded events.")


def render(state: AppState, detector=None) -> None:
    st.header("Nurse dashboard")
    st.caption("Simulated time: " + format_time(state.simulated_time))

    patient_ids = render_patient_list(state)

    patient_id = st.selectbox(
        "Inspect patient",
        options=patient_ids,
        format_func=lambda value: state.patients[value].name,
        key="nurse_patient",
    )

    st.divider()
    st.subheader(state.patients[patient_id].name)

    monitoring = monitoring_summary(state, patient_id)

    if monitoring["status"] in (
        "Monitoring unavailable",
        "AI analysis unavailable",
    ):
        st.warning(
            monitoring["status"] + " — " + monitoring["detail"]
        )
    else:
        st.write("**" + monitoring["status"] + "**")

    st.caption(
        "Last usable measurement: " + monitoring["last_usable"]
    )

    render_checkin(state, patient_id)

    st.subheader("Wearable trends")

    frame = build_chart_data(state, patient_id, detector)

    if frame.empty:
        st.info("No completed measurement windows.")
    else:
        st.plotly_chart(
            build_trend_figure(frame),
            use_container_width=True,
            key=f"trends_{patient_id}",
            config={
                "displaylogo": False,
                "scrollZoom": False,
            },
        )

        st.caption(
            "Each point represents a completed four-hour window. "
            "Gaps indicate absent or unusable measurements. "
            "Historical readings are not evidence of current monitoring."
        )

        if detector is None:
            st.caption("Personal baseline comparison is unavailable.")
        else:
            st.caption(
                "Dashed lines show fixed personal reference values "
                "for the corresponding time slot, not clinical limits."
            )

    render_reviews(state, patient_id)
    render_audit(state, patient_id)