"""Smoke test for application startup and screen navigation."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_startup_and_navigation() -> None:
    app = AppTest.from_file(str(APP_PATH)).run()

    assert not app.exception
    assert app.title[0].value == "Oncology Watch"
    assert app.header[0].value == "Patient"

    app.radio[0].set_value("Nurse dashboard").run()

    assert not app.exception
    assert app.header[0].value == "Nurse dashboard"

    app.radio[0].set_value("Patient").run()

    assert not app.exception
    assert app.header[0].value == "Patient"