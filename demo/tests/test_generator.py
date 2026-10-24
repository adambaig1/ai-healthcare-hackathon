import csv
import json
from datetime import timedelta

from domain import ConnectionStatus, Feeling
from scripts.generate_data import (
    DEMO_START,
    EVENT_WINDOW_INDEX,
    PATIENTS,
    generate_all,
    generate_checkins,
    generate_windows,
)


def test_generation_is_reproducible():
    first = generate_windows("example", DEMO_START, 2, seed=42)
    second = generate_windows("example", DEMO_START, 2, seed=42)

    assert first == second
    assert len(first) == 2 * 6 * len(PATIENTS)
    assert len({window.id for window in first}) == len(first)


def test_windows_are_adjacent_and_four_hours_long():
    windows = generate_windows("example", DEMO_START, 2, seed=42)

    for patient in PATIENTS:
        patient_windows = [
            window for window in windows
            if window.patient_id == patient.id
        ]

        for window in patient_windows:
            assert window.end - window.start == timedelta(hours=4)

        for previous, current in zip(
            patient_windows, patient_windows[1:]
        ):
            assert previous.end == current.start


def test_disconnect_has_missing_measurements():
    windows = generate_windows(
        "disconnect",
        DEMO_START,
        2,
        seed=42,
        scenario="wearable_disconnect",
    )

    onset = DEMO_START + timedelta(hours=4 * EVENT_WINDOW_INDEX)

    affected = [
        window for window in windows
        if window.patient_id == "patient-001"
        and window.start >= onset
    ]

    assert affected

    for window in affected:
        assert window.connection == ConnectionStatus.DISCONNECTED
        assert window.resting_hr is None
        assert window.steps is None
        assert window.coverage_percent == 0


def test_exercise_changes_activity_not_resting_hr():
    ordinary = generate_windows(
        "comparison", DEMO_START, 2, seed=42
    )
    exercise = generate_windows(
        "comparison",
        DEMO_START,
        2,
        seed=42,
        scenario="brief_exercise",
    )

    changed = [
        (before, after)
        for before, after in zip(ordinary, exercise)
        if before.steps != after.steps
    ]

    assert len(changed) == 1

    before, after = changed[0]
    assert after.steps > before.steps
    assert after.resting_hr == before.resting_hr


def test_sustained_change_affects_multiple_windows():
    ordinary = generate_windows(
        "comparison", DEMO_START, 2, seed=42
    )
    changed = generate_windows(
        "comparison",
        DEMO_START,
        2,
        seed=42,
        scenario="sustained_change",
    )

    affected_pairs = [
        (before, after)
        for before, after in zip(ordinary, changed)
        if before.resting_hr != after.resting_hr
    ]

    assert len(affected_pairs) == 4

    for before, after in affected_pairs:
        assert after.patient_id == "patient-001"
        assert after.resting_hr > before.resting_hr
        assert after.steps < before.steps


def test_unwell_checkin_does_not_change_wearable_readings():
    ordinary = generate_windows(
        "comparison", DEMO_START, 2, seed=42
    )
    unwell = generate_windows(
        "comparison",
        DEMO_START,
        2,
        seed=42,
        scenario="unwell_ordinary",
    )

    assert ordinary == unwell

    checkins = generate_checkins(
        "comparison", DEMO_START, "unwell_ordinary"
    )

    assert len(checkins) == 1
    assert checkins[0].feeling == Feeling.UNWELL
    assert checkins[0].temperature_c is None


def test_written_fixtures_are_reproducible_and_separate(tmp_path):
    generate_all(tmp_path)

    first_contents = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    generate_all(tmp_path)

    second_contents = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert first_contents == second_contents

    # IDs across reference, calibration, demo and evaluation must not collide.
    all_ids = []

    for path in tmp_path.rglob("*.csv"):
        with path.open(newline="", encoding="utf-8") as handle:
            all_ids.extend(row["id"] for row in csv.DictReader(handle))

    assert len(all_ids) == len(set(all_ids))

    manifest = json.loads(
        (tmp_path / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["reference_rows"] == 252
    assert manifest["calibration_rows"] == 126
    assert manifest["rows_per_scenario"] == 36

    disconnect_path = (
        tmp_path / "scenarios" / "wearable_disconnect" / "windows.csv"
    )

    with disconnect_path.open(newline="", encoding="utf-8") as handle:
        disconnected = [
            row for row in csv.DictReader(handle)
            if row["connection"] == "disconnected"
        ]

    assert disconnected
    assert all(row["resting_hr"] == "" for row in disconnected)
    assert all(row["steps"] == "" for row in disconnected)