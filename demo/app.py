"""Run with: streamlit run app.py."""

import streamlit as st

from config import APP_NAME
from simulation import (
    advance_one_day,
    create_demo,
    next_event_time,
    run_to_next_event,
)
from views import nurse, patient


SCENARIO_LABELS = {
    "golden_path": "28-Day Chemo Narrative",
}


def main() -> None:
    st.set_page_config(
        page_title=APP_NAME,
        page_icon="🔎",
        layout="wide",
    )

    st.title(APP_NAME)

    st.warning(
        "Synthetic demonstration only. "
        "Not a clinical monitoring service."
    )

    st.caption(
        "Synthetic wearable monitoring, patient check-ins "
        "and recorded nurse review."
    )

    with st.sidebar:
        st.header("Workspace")

        screen = st.radio(
            "Screen",
            options=["Patient", "Nurse dashboard"],
            key="screen",
        )

        st.divider()
        st.header("Demonstration")

        scenario_name = st.selectbox(
            "Scenario",
            options=list(SCENARIO_LABELS),
            format_func=lambda value: SCENARIO_LABELS[value],
            key="scenario_choice",
        )

        reset_clicked = st.button(
            "Reset scenario",
            key="reset_scenario",
        )

    controller = st.session_state.get("demo_controller")

    expected_id = f"scenarios-{scenario_name}"

    scenario_changed = (
        controller is not None
        and controller.session.state.scenario_id != expected_id
    )

    if reset_clicked or scenario_changed:
        # Clear runtime and old widget inputs, but preserve navigation.
        st.session_state.clear()
        st.session_state["screen"] = screen
        st.session_state["scenario_choice"] = scenario_name
        st.rerun()

    if controller is None:
        try:
            with st.spinner("Preparing the synthetic demonstration..."):
                controller = create_demo(scenario_name)
        except (OSError, ValueError, KeyError, TypeError) as error:
            st.error(f"Could not prepare the demonstration: {error}")
            st.code("python -m scripts.generate_data", language="bash")
            st.stop()

        st.session_state["demo_controller"] = controller

    session = controller.session
    state = session.state

    # Define the narrative text for your specific demo milestones
    NARRATIVE_STORY = {
        1: "Day 1: Chemotherapy starts. Alex Morgan establishes a healthy baseline.",
        7: "Day 7: Alex feels mostly well. Vitals are stable. Coverage is high.",
        14: "Day 14: AI flags physiological deterioration. Alex checks in with fever and chills. RED ALERT triggered.",
        15: "Day 15: Nurse conducts review. Action recorded. Alex continues monitoring.",
        21: "Day 21: Alex's recovery observed. Vitals returning to baseline.",
        28: "Day 28: Alex is stable."
    }

    with st.sidebar:
        finished = state.simulated_time >= session.scenario.end_time
        
        demo_start = session.scenario.start_time
        current_day = (state.simulated_time - demo_start).days + 1

        if st.button(
            "Advance 1 Day",
            key="advance_one_day",
            disabled=finished,
        ):
            advance_one_day(controller)
            st.rerun()

        if st.button(
            "Run to next event",
            key="run_to_next_event",
            disabled=finished,
        ):
            run_to_next_event(controller)
            
            # Recalculate day after advancing to see if we hit a story milestone
            new_day = (controller.session.state.simulated_time - demo_start).days + 1
            if new_day in NARRATIVE_STORY:
                st.session_state["story_toast"] = NARRATIVE_STORY[new_day]
                
                # 2. UX FIX: Auto-snap the Nurse dropdown back to Alex Morgan
                # so the judges immediately see the emergency charts!
                st.session_state["nurse_patient"] = "patient-001"
            
            st.rerun()
            
        if "story_toast" in st.session_state:
            st.toast(f" **Narrative Update:** {st.session_state.pop('story_toast')}")

        st.caption(
            "Simulated time: "
            + state.simulated_time.strftime("%d %b %Y, %H:%M %Z")
        )

        next_time = next_event_time(controller)

        if next_time is not None:
            st.caption(
                "Next event: "
                + next_time.strftime("%d %b %Y, %H:%M %Z")
            )
        else:
            st.caption("Scenario complete. Reset to replay.")

        st.caption(
            "Switching scenarios starts a fresh session. "
            "All displayed times use UTC."
        )

    if controller.engine.startup_error:
        st.warning(
            "AI analysis unavailable. "
            "Patient check-ins and nurse review actions remain available."
        )

    if screen == "Patient":
        patient.render(state)
    else:
        nurse.render(
            state,
            detector=controller.engine.detector,
        )


if __name__ == "__main__":
    main()