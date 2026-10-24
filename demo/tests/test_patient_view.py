from pathlib import Path

from streamlit.testing.v1 import AppTest

from domain import Feeling
from scripts.generate_data import generate_all
from simulation import create_demo, run_to_next_event


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def prepare_app(tmp_path, scenario="sustained_change"):
    generate_all(tmp_path)
    controller = create_demo(scenario, root=tmp_path)

    app = AppTest.from_file(str(APP_PATH))
    app.session_state["demo_controller"] = controller
    app.session_state["scenario_choice"] = scenario
    app.run()

    assert not app.exception
    return app


def test_unwell_button_creates_checkin_and_review(tmp_path):
    app = prepare_app(tmp_path)

    app.button(key="report_unwell").click().run()

    assert not app.exception

    state = app.session_state["demo_controller"].session.state

    assert len(state.checkins) == 1
    assert next(iter(state.checkins.values())).feeling == Feeling.UNWELL
    assert len(state.reviews) == 1

    assert any(
        "clinician" in warning.value
        for warning in app.warning
    )


def test_invalid_temperature_does_not_submit_checkin(tmp_path):
    app = prepare_app(tmp_path)

    app.text_input(
        key="patient_checkin_0_temperature"
    ).set_value("not a number")

    app.button(key="patient_checkin_0_submit").click().run()

    assert not app.exception

    state = app.session_state["demo_controller"].session.state

    assert not state.checkins
    assert app.error
    assert (
        app.text_input(key="patient_checkin_0_temperature").value
        == "not a number"
    )


def test_worse_checkin_requires_no_temperature(tmp_path):
    app = prepare_app(tmp_path)

    app.radio(
        key="patient_checkin_0_feeling"
    ).set_value(Feeling.WORSE)

    app.button(key="patient_checkin_0_submit").click().run()

    assert not app.exception

    state = app.session_state["demo_controller"].session.state
    checkin = next(iter(state.checkins.values()))

    assert checkin.feeling == Feeling.WORSE
    assert checkin.temperature_c is None
    assert len(state.reviews) == 1

    # Successful submission resets the form.
    assert app.radio(
        key="patient_checkin_1_feeling"
    ).value == Feeling.USUAL


def test_unwell_button_works_during_disconnect(tmp_path):
    generate_all(tmp_path)

    controller = create_demo(
        "wearable_disconnect",
        root=tmp_path,
    )
    run_to_next_event(controller)

    app = AppTest.from_file(str(APP_PATH))
    app.session_state["demo_controller"] = controller
    app.session_state["scenario_choice"] = "wearable_disconnect"
    app.run()

    assert not app.exception
    assert any(
        "Monitoring unavailable" in item.value
        for item in app.markdown
    )

    app.button(key="report_unwell").click().run()

    assert not app.exception

    state = app.session_state["demo_controller"].session.state

    assert len(state.checkins) == 1
    assert any(
        review.patient_id == "patient-001" and review.is_open
        for review in state.reviews.values()
    )