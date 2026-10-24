"""Nurse dashboard interface."""

import streamlit as st


def render() -> None:
    st.header("Nurse dashboard")

    st.info("No synthetic patient records or review tasks loaded yet.")

    st.subheader("Coming next")
    st.write(
        "Patient trends, supporting observations, "
        "review actions and audit history."
    )

    st.caption(
        "Monitoring status and review status "
        "will be displayed separately."
    )