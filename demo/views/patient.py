"""Patient interface for the synthetic Oncology Watch demonstration."""

import streamlit as st

from domain import (
    AppState,
    ConnectionStatus,
    Feeling,
    new_id,
)
from monitoring import monitoring_summary
from services import submit_checkin


PATIENT_ID = "patient-001"

FEELING_LABELS = {
    Feeling.USUAL: "About usual",
    Feeling.WORSE: "Worse than usual",
    Feeling.UNWELL: "Unwell",
}

CONNECTION_LABELS = {
    ConnectionStatus.CONNECTED: "Connected",
    ConnectionStatus.DISCONNECTED: "Disconnected",
    ConnectionStatus.UNKNOWN: "Unknown",
}

SYMPTOMS = (
    "Feeling generally unwell",
    "Chills",
    "Worsening fatigue",
    "Other concern",
)


def format_time(timestamp) -> str:
    return timestamp.strftime("%d %b %Y, %H:%M UTC")


def latest_patient_window(state: AppState):
    windows = [
        window
        for window in state.windows.values()
        if window.patient_id == PATIENT_ID
        and window.end <= state.simulated_time
    ]

    return max(windows, key=lambda window: window.end, default=None)


def render_contact_instructions() -> None:
    st.markdown(
        "**If you feel unwell, follow the oncology contact instructions "
        "provided by your care team. Do not wait for this app, an AI flag "
        "or a temperature reading.**"
    )

    st.caption(
        "Demo only: no clinical team is connected and no call or message "
        "will be sent."
    )


def render_monitoring(state: AppState) -> None:
    latest = latest_patient_window(state)
    summary = monitoring_summary(state, PATIENT_ID)

    with st.container(border=True):
        st.subheader("Wearable and monitoring")

        connection_column, monitoring_column = st.columns(2)

        with connection_column:
            st.markdown("**Wearable connection**")

            if latest is None:
                st.write("No connection report available")
            else:
                st.write(CONNECTION_LABELS[latest.connection])
                st.caption(
                    "Reported for the window ending "
                    + format_time(latest.end)
                )

        with monitoring_column:
            st.markdown("**Monitoring status**")
            st.write(summary["status"])
            st.caption(summary["detail"])

        if summary["status"] == "Monitoring unavailable":
            st.warning(
                "Recent usable measurements are unavailable. "
                "This does not mean that you are well."
            )
        elif summary["status"] == "AI analysis unavailable":
            st.warning(
                "Measurements are available, but AI analysis is unavailable. "
                "You can still submit a check-in."
            )
        elif summary["status"] == "Monitoring available":
            st.caption(
                "Monitoring availability describes the data connection "
                "and analysis, not your health."
            )

        st.caption(
            "Last usable measurement: "
            + summary["last_usable"]
        )

        if latest is not None:
            st.caption(
                "Coverage in the latest four-hour window: "
                + (
                    f"{latest.coverage_percent:g}%"
                    if latest.coverage_percent is not None
                    else "Not reported"
                )
            )

        st.caption(
            "This demo records measurement windows, not device sync events."
        )


def render_unwell_action(state: AppState) -> None:
    with st.container(border=True):
        st.subheader("Feeling unwell?")
        render_contact_instructions()

        if st.button(
            "I feel unwell",
            type="primary",
            key="report_unwell",
        ):
            try:
                submit_checkin(
                    state,
                    command_id=new_id(),
                    patient_id=PATIENT_ID,
                    feeling=Feeling.UNWELL,
                )
            except ValueError as error:
                st.error(f"Check-in was not saved: {error}")
            else:
                st.success("Your unwell check-in was saved to this demo.")
                st.warning(
                    "Follow your oncology contact instructions. "
                    "Saving a check-in does not mean a clinician "
                    "has reviewed it."
                )


def render_checkin_form(state: AppState) -> None:
    # Changing the form version after success gives the next submission
    # fresh widgets. Failed validation keeps the current inputs intact.
    version = st.session_state.get("patient_form_version", 0)
    prefix = f"patient_checkin_{version}"

    with st.form(prefix):
        st.subheader("Daily check-in")
        st.caption(
            "Tell us how you feel. A wearable reading or temperature "
            "is not required."
        )

        feeling = st.radio(
            "How are you feeling?",
            options=list(Feeling),
            format_func=lambda value: FEELING_LABELS[value],
            key=f"{prefix}_feeling",
        )

        symptoms = st.multiselect(
            "Symptoms or concerns",
            options=SYMPTOMS,
            key=f"{prefix}_symptoms",
        )

        temperature_text = st.text_input(
            "Temperature in °C — optional",
            placeholder="For example, 36.8",
            help=(
                "Enter a reading from a separate thermometer, "
                "or leave this blank."
            ),
            key=f"{prefix}_temperature",
        )

        st.caption(
            "Temperature is recorded for review. This prototype does "
            "not apply clinical temperature thresholds."
        )

        submitted = st.form_submit_button(
            "Submit check-in",
            key=f"{prefix}_submit",
        )

    if not submitted:
        return

    try:
        temperature = (
            float(temperature_text.strip())
            if temperature_text.strip()
            else None
        )
    except ValueError:
        st.error(
            "Enter temperature as a number, such as 36.8, "
            "or leave it blank. Your check-in has not been saved."
        )
        return

    try:
        submit_checkin(
            state,
            command_id=new_id(),
            patient_id=PATIENT_ID,
            feeling=feeling,
            symptoms=tuple(symptoms),
            temperature_c=temperature,
        )
    except ValueError as error:
        st.error(f"Check-in was not saved: {error}")
        return

    st.session_state["patient_form_version"] = version + 1
    st.session_state["patient_submission_notice"] = True
    st.rerun()


def render_recent_checkins(state: AppState) -> None:
    checkins = [
        checkin
        for checkin in state.checkins.values()
        if checkin.patient_id == PATIENT_ID
    ]

    st.subheader("Your recent check-ins")

    if not checkins:
        st.info("No check-ins submitted in this demo session.")
        return

    latest = checkins[-1]

    if latest.feeling == Feeling.UNWELL:
        st.warning(
            "Your latest check-in says you feel unwell. "
            "Follow your oncology contact instructions rather than "
            "waiting for this demonstration to be reviewed."
        )

    rows = [
        {
            "Submitted — UTC": format_time(checkin.timestamp),
            "Feeling": FEELING_LABELS[checkin.feeling],
            "Symptoms": (
                ", ".join(checkin.symptoms)
                if checkin.symptoms
                else "None selected"
            ),
            "Temperature": (
                f"{checkin.temperature_c:g} °C"
                if checkin.temperature_c is not None
                else "Not provided"
            ),
        }
        for checkin in reversed(checkins[-5:])
    ]

    st.dataframe(rows, hide_index=True, width="stretch")

    st.caption(
        "These are submitted reports, not confirmations of clinical review. "
        "Resetting the scenario clears this history."
    )


def render(state: AppState) -> None:
    st.header("Patient")

    patient = state.patients[PATIENT_ID]

    st.subheader(f"Hello, {patient.name}")
    st.caption(
        "Fictional patient · Simulated time: "
        + format_time(state.simulated_time)
    )

    render_unwell_action(state)

    if st.session_state.pop("patient_submission_notice", False):
        st.success("Your check-in was saved to this demo.")
        st.info(
            "Submission does not mean a clinician has reviewed it. "
            "This prototype sends no calls or messages."
        )

    render_monitoring(state)
    render_checkin_form(state)
    render_recent_checkins(state)