"""Run with: streamlit run app.py."""

import streamlit as st

from config import APP_NAME
from views import nurse, patient


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
        "Phase 1: project foundation. "
        "Patient data and AI are not implemented yet."
    )

    with st.sidebar:
        st.header("Workspace")

        screen = st.radio(
            "Screen",
            options=["Patient", "Nurse dashboard"],
            key="screen",
        )

        st.divider()

        st.caption(
            "Local, single-session prototype. "
            "No external services."
        )

    if screen == "Patient":
        patient.render()
    else:
        nurse.render()


if __name__ == "__main__":
    main()