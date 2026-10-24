"""Test navigation and runtime preservation."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from scripts.generate_data import generate_all
from simulation import create_demo


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_startup_and_navigation(tmp_path):
    generate_all(tmp_path)
    controller = create_demo(root=tmp_path)

    controller.session.state.processed_command_ids.add("test-marker")

    app = AppTest.from_file(str(APP_PATH))
    app.session_state["demo_controller"] = controller
    app.run()

    assert not app.exception
    assert app.title[0].value == "Oncology Watch"
    assert app.header[0].value == "Patient"

    app.radio(key="screen").set_value("Nurse dashboard").run()

    assert not app.exception
    assert app.header[0].value == "Nurse dashboard"

    app.radio(key="screen").set_value("Patient").run()

    assert not app.exception
    assert app.header[0].value == "Patient"

    retained = app.session_state["demo_controller"]

    assert (
        "test-marker"
        in retained.session.state.processed_command_ids
    )
    assert len(retained.session.state.assessments) == 3

    app.button(key="advance_four_hours").click().run()

    assert not app.exception

    advanced = app.session_state["demo_controller"]
    assert len(advanced.session.state.assessments) == 6