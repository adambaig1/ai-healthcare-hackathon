"""Patient interface for the synthetic Oncology Watch demonstration."""

import streamlit as st

from domain import (
    AppState,
    ConnectionStatus,
    Feeling,
    Symptom,
    new_id,
)
from monitoring import monitoring_summary
from services import submit_checkin


FEELING_LABELS = {
    Feeling.WELL: "1 - Well",
    Feeling.MOSTLY_WELL: "2 - Mostly well",
    Feeling.NOT_WELL: "3 - Not feeling well",
    Feeling.VERY_UNWELL: "4 - Feeling very unwell",
    Feeling.EXTREMELY_UNWELL: "5 - Feeling extremely unwell",
}

CONNECTION_LABELS = {
    ConnectionStatus.CONNECTED: "Connected",
    ConnectionStatus.DISCONNECTED: "Disconnected",
    ConnectionStatus.UNKNOWN: "Unknown",
}

# Cleanly format the Enum names for the multiselect box
SYMPTOMS = [s.name.replace("_", " ").title() for s in Symptom]


def format_time(timestamp) -> str:
    return timestamp.strftime("%d %b %Y, %H:%M UTC")


def latest_patient_window(state: AppState, patient_id: str):
    windows = [
        window
        for window in state.windows.values()
        if window.patient_id == patient_id
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


def render_monitoring(state: AppState, patient_id: str) -> None:
    latest = latest_patient_window(state, patient_id)
    summary = monitoring_summary(state, patient_id)

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


def render_unwell_action(state: AppState, patient_id: str) -> None:
    with st.container(border=True):
        st.subheader("Feeling unwell?")
        render_contact_instructions()

        if st.button(
            "I feel unwell",
            type="primary",
            key=f"report_unwell_{patient_id}",
        ):
            try:
                submit_checkin(
                    state,
                    command_id=new_id(),
                    patient_id=patient_id,
                    feeling=Feeling.EXTREMELY_UNWELL.value,
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


def render_checkin_form(state: AppState, patient_id: str) -> None:
    version = st.session_state.get("patient_form_version", 0)
    prefix = f"patient_checkin_{patient_id}_{version}"

    with st.form(prefix):
        st.subheader("Daily check-in")
        st.caption(
            "Tell us how you feel. A wearable reading or temperature "
            "is not required."
        )

        feeling_val = st.select_slider(
            "How are you feeling today?",
            options=[f.value for f in Feeling],
            format_func=lambda value: FEELING_LABELS[Feeling(value)],
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

    # Map the selected string labels back to the enum values for storage
    selected_symptom_enums = [
        s.value for s in Symptom if s.name.replace("_", " ").title() in symptoms
    ]

    try:
        submit_checkin(
            state,
            command_id=new_id(),
            patient_id=patient_id,
            feeling=feeling_val,
            symptoms=tuple(selected_symptom_enums),
            temperature_c=temperature,
        )
    except ValueError as error:
        st.error(f"Check-in was not saved: {error}")
        return

    st.session_state["patient_form_version"] = version + 1
    st.session_state["patient_submission_notice"] = True
    st.rerun()


def render_recent_checkins(state: AppState, patient_id: str) -> None:
    checkins = [
        checkin
        for checkin in state.checkins.values()
        if checkin.patient_id == patient_id
    ]

    st.subheader("Your recent check-ins")

    if not checkins:
        st.info("No check-ins submitted in this demo session.")
        return

    latest = checkins[-1]

    if latest.feeling >= Feeling.VERY_UNWELL.value:
        st.warning(
            "Your latest check-in says you feel very unwell. "
            "Follow your oncology contact instructions rather than "
            "waiting for this demonstration to be reviewed."
        )

    rows = [
        {
            "Submitted — UTC": format_time(checkin.timestamp),
            "Feeling": FEELING_LABELS[Feeling(checkin.feeling)],
            "Symptoms": (
                ", ".join([Symptom(s).name.replace("_", " ").title() for s in checkin.symptoms])
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
    st.header("Patient View")

    # Add a dropdown to switch between patients
    patient_ids = sorted(list(state.patients.keys()))
    patient_id = st.selectbox(
        "View App As",
        options=patient_ids,
        format_func=lambda pid: state.patients[pid].name,
        key="patient_view_selector",
    )

    patient = state.patients[patient_id]

    st.subheader(f"Hello, {patient.name}")
    st.caption(
        "Fictional patient · Simulated time: "
        + format_time(state.simulated_time)
    )

    render_unwell_action(state, patient_id)

    if st.session_state.pop("patient_submission_notice", False):
        st.success("Your check-in was saved to this demo.")
        st.info(
            "Submission does not mean a clinician has reviewed it. "
            "This prototype sends no calls or messages."
        )

    # UI REORDER: Check-ins are now placed above Wearable monitoring
    render_checkin_form(state, patient_id)
    render_recent_checkins(state, patient_id)
    
    render_monitoring(state, patient_id)