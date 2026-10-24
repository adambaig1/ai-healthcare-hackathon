"""Patient interface."""

import streamlit as st


def render() -> None:
    st.header("Patient")

    st.info("No synthetic patient loaded yet.")

    st.subheader("Coming next")
    st.write(
        "Wearable connection status, a symptom check-in "
        "and optional temperature entry."
    )

    st.caption(
        "No check-ins are being submitted or reviewed "
        "in this starter version."
    )