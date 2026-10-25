"""Fixture loading and temporary session storage.

This module does not import Streamlit.
"""

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config import FIXTURES_DIR
from domain import (
    AppState,
    CheckIn,
    ConnectionStatus,
    Feeling,
    Patient,
    Symptom,
    WearableWindow,
    require_aware,
)


SCENARIO_NAMES = ("golden_path",)



def parse_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value)
    require_aware(timestamp)
    return timestamp


def optional_float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value)


def optional_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    return int(value)


def require_unique_ids(records) -> None:
    ids = [record.id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Fixture contains duplicate record IDs.")


def load_patients(path: Path) -> dict[str, Patient]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    patients = [Patient(**row) for row in rows]

    require_unique_ids(patients)

    return {patient.id: patient for patient in patients}


def load_windows(path: Path) -> tuple[WearableWindow, ...]:
    windows = []

    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            windows.append(
                WearableWindow(
                    id=row["id"],
                    patient_id=row["patient_id"],
                    start=parse_timestamp(row["start"]),
                    end=parse_timestamp(row["end"]),
                    resting_hr=optional_float(row["resting_hr"]),
                    steps=optional_int(row["steps"]),
                    coverage_percent=optional_float(
                        row["coverage_percent"]
                    ),
                    connection=ConnectionStatus(row["connection"]),
                )
            )

    require_unique_ids(windows)

    # Different IDs must not disguise duplicate patient/time windows.
    keys = [
        (window.patient_id, window.start, window.end)
        for window in windows
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("Fixture contains duplicate patient windows.")

    return tuple(
        sorted(windows, key=lambda window: (window.end, window.patient_id))
    )


def load_checkins(path: Path) -> tuple[CheckIn, ...]:
    rows = json.loads(path.read_text(encoding="utf-8"))

    checkins = [
        CheckIn(
            id=row["id"],
            patient_id=row["patient_id"],
            timestamp=parse_timestamp(row["timestamp"]),
            feeling=Feeling(int(row["feeling"])),
            symptoms=tuple(Symptom(s) for s in row["symptoms"]),
            temperature_c=(
                None
                if row["temperature_c"] is None
                else float(row["temperature_c"])
            ),
        )
        for row in rows
    ]

    require_unique_ids(checkins)

    return tuple(
        sorted(checkins, key=lambda checkin: (checkin.timestamp, checkin.id))
    )


@dataclass(frozen=True)
class ScenarioData:
    """Fixed input events. These are not current session records."""

    id: str
    start_time: datetime
    end_time: datetime
    initial_time: datetime
    windows: tuple[WearableWindow, ...]
    checkins: tuple[CheckIn, ...]
    event_times: tuple[datetime, ...] = ()


@dataclass
class DemoSession:
    """Fixed fixtures plus a fresh, mutable runtime state."""

    state: AppState
    scenario: ScenarioData
    reference: tuple[WearableWindow, ...]
    calibration: tuple[WearableWindow, ...]


def load_scenario(
    scenario_name: str,
    root: Path = FIXTURES_DIR,
) -> ScenarioData:
    if scenario_name not in SCENARIO_NAMES:
        raise ValueError(f"Unknown scenario: {scenario_name}")

    directory = root / "scenarios" / scenario_name

    metadata = json.loads(
        (directory / "metadata.json").read_text(encoding="utf-8")
    )

    scenario = ScenarioData(
        id=metadata["dataset_id"],
        start_time=parse_timestamp(metadata["start_time"]),
        end_time=parse_timestamp(metadata["end_time"]),
        initial_time=parse_timestamp(
            metadata["initial_simulated_time"]
        ),
        windows=load_windows(directory / "windows.csv"),
        checkins=load_checkins(directory / "checkins.json"),
        event_times=tuple(
            sorted(
                {
                    parse_timestamp(event["timestamp"])
                    for event in metadata.get("events", [])
                }
            )
        ),
    )

    if not (
        scenario.start_time
        <= scenario.initial_time
        <= scenario.end_time
    ):
        raise ValueError("Initial simulated time is outside the scenario.")

    for window in scenario.windows:
        if not (
            scenario.start_time
            <= window.start
            < window.end
            <= scenario.end_time
        ):
            raise ValueError("Wearable window is outside the scenario.")

    for checkin in scenario.checkins:
        if not (
            scenario.start_time
            <= checkin.timestamp
            <= scenario.end_time
        ):
            raise ValueError("Check-in is outside the scenario.")

    for timestamp in scenario.event_times:
        if not scenario.start_time <= timestamp <= scenario.end_time:
            raise ValueError("Event marker is outside the scenario.")

    return scenario

def create_session(
    scenario_name: str = "sustained_change",
    root: Path = FIXTURES_DIR,
) -> DemoSession:
    """Create fresh state without scoring data or submitting check-ins."""
    patients = load_patients(root / "patients.json")
    reference = load_windows(root / "reference.csv")
    calibration = load_windows(root / "calibration.csv")
    scenario = load_scenario(scenario_name, root)

    all_records = (
        *reference,
        *calibration,
        *scenario.windows,
        *scenario.checkins,
    )

    require_unique_ids(all_records)

    for record in all_records:
        if record.patient_id not in patients:
            raise ValueError(
                f"Unknown patient in fixture: {record.patient_id}"
            )

    if not reference or not calibration:
        raise ValueError("Reference and calibration data must not be empty.")

    if max(window.end for window in reference) > min(
        window.start for window in calibration
    ):
        raise ValueError("Reference and calibration periods overlap.")

    if max(window.end for window in calibration) > scenario.start_time:
        raise ValueError("Calibration extends into the demo period.")

    state = AppState(
        scenario_id=scenario.id,
        simulated_time=scenario.initial_time,
        patients=patients,
    )

    # Only completed windows are visible to the runtime.
    state.windows = {
        window.id: window
        for window in scenario.windows
        if window.end <= state.simulated_time
    }

    # No assessments, reviews or check-ins are created here.
    # Phase 5+ services will process due events exactly once.
    return DemoSession(
        state=state,
        scenario=scenario,
        reference=reference,
        calibration=calibration,
    )