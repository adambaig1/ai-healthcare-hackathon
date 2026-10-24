import csv
import json

import pytest

from data import create_session, load_windows
from scripts.generate_data import generate_all


@pytest.fixture
def fixture_root(tmp_path):
    generate_all(tmp_path)
    return tmp_path


def test_session_loads_expected_data(fixture_root):
    session = create_session(root=fixture_root)

    assert len(session.state.patients) == 3
    assert len(session.reference) == 252
    assert len(session.calibration) == 126
    assert len(session.scenario.windows) == 36

    # Initial time is after one completed window per patient.
    assert len(session.state.windows) == 3
    assert not session.state.assessments
    assert not session.state.reviews
    assert not session.state.audit_events
    assert not session.state.processed_window_ids


def test_future_readings_are_not_exposed_in_runtime(fixture_root):
    session = create_session(root=fixture_root)

    assert all(
        window.end <= session.state.simulated_time
        for window in session.state.windows.values()
    )

    assert any(
        window.end > session.state.simulated_time
        for window in session.scenario.windows
    )


def test_scripted_checkin_is_not_submitted_during_loading(fixture_root):
    session = create_session(
        scenario_name="unwell_ordinary",
        root=fixture_root,
    )

    assert len(session.scenario.checkins) == 1
    assert not session.state.checkins
    assert not session.state.reviews


def test_missing_csv_measurements_load_as_none(fixture_root):
    windows = load_windows(
        fixture_root
        / "scenarios"
        / "wearable_disconnect"
        / "windows.csv"
    )

    disconnected = [
        window
        for window in windows
        if window.connection.value == "disconnected"
    ]

    assert disconnected
    assert all(window.resting_hr is None for window in disconnected)
    assert all(window.steps is None for window in disconnected)


def test_creating_a_session_restores_fresh_runtime(fixture_root):
    first = create_session(root=fixture_root)

    first.state.processed_window_ids.add("example-window")
    first.state.windows.clear()

    second = create_session(root=fixture_root)

    assert not second.state.processed_window_ids
    assert len(second.state.windows) == 3

    assert first.scenario == second.scenario
    assert first.state is not second.state


def test_duplicate_window_ids_are_rejected(fixture_root):
    path = fixture_root / "reference.csv"

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)

    rows.append(rows[0].copy())

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="duplicate"):
        load_windows(path)


def test_unknown_patient_reference_is_rejected(fixture_root):
    path = fixture_root / "patients.json"
    patients = json.loads(path.read_text(encoding="utf-8"))

    path.write_text(
        json.dumps(patients[1:]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unknown patient"):
        create_session(root=fixture_root)