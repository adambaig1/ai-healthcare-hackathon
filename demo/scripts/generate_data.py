"""Generate reproducible synthetic fixtures.

Run from the project directory:
    python -m scripts.generate_data

No real patient data or external sources are used.
"""

import csv
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import numpy as np

from config import FIXTURES_DIR, SETTINGS
from domain import (
    CheckIn,
    ConnectionStatus,
    Feeling,
    Patient,
    WearableWindow,
)


PATIENTS = (
    Patient("patient-001", "Alex Morgan", "baseline-001"),
    Patient("patient-002", "Sam Taylor", "baseline-002"),
    Patient("patient-003", "Jamie Ellis", "baseline-003"),
)

# Fictional resting-HR centres and activity multipliers.
PROFILES = {
    "patient-001": (70.0, 1.0),
    "patient-002": (77.0, 0.7),
    "patient-003": (64.0, 1.3),
}

# Slots start at 00:00, 04:00, 08:00, 12:00, 16:00 and 20:00.
HR_SLOT_OFFSETS = (-4.0, -3.0, 1.0, 2.0, 1.0, -1.0)
STEP_SLOT_CENTRES = (15, 80, 1000, 1500, 1100, 250)

SCENARIOS = (
    "sustained_change",
    "brief_exercise",
    "wearable_disconnect",
    "unwell_ordinary",
)

# Changes start at 08:00 on the second scenario day.
EVENT_WINDOW_INDEX = 8
SCENARIO_DAYS = 2

REFERENCE_START = datetime(2026, 9, 1, tzinfo=timezone.utc)
CALIBRATION_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
DEMO_START = datetime(2026, 10, 24, tzinfo=timezone.utc)
EVALUATION_START = datetime(2026, 11, 1, tzinfo=timezone.utc)

WINDOW_FIELDS = [
    "id",
    "patient_id",
    "start",
    "end",
    "resting_hr",
    "steps",
    "coverage_percent",
    "connection",
]


def stable_id(*parts: object) -> str:
    """Same fixture and event always produce the same ID."""
    key = "|".join(str(part) for part in parts)
    return str(uuid5(NAMESPACE_URL, f"oncology-watch|{key}"))


def ordinary_measurements(
    rng: np.random.Generator,
    patient_id: str,
    slot: int,
    day_hr_offset: float,
    day_activity_factor: float,
) -> tuple[float, int]:
    """Generate ordinary variation around a fictional daily pattern."""
    hr_centre, activity_multiplier = PROFILES[patient_id]

    resting_hr = (
        hr_centre
        + HR_SLOT_OFFSETS[slot]
        + day_hr_offset
        + rng.normal(0, 1.8)
    )

    steps = (
        STEP_SLOT_CENTRES[slot]
        * activity_multiplier
        * day_activity_factor
        * rng.lognormal(mean=0, sigma=0.25)
    )

    # This is a resting observation, not exercise heart rate.
    return round(float(resting_hr), 1), max(0, int(round(steps)))


def generate_windows(
    dataset_id: str,
    start: datetime,
    days: int,
    seed: int,
    scenario: str | None = None,
) -> list[WearableWindow]:
    """Generate chronological four-hour windows with stable IDs."""
    if scenario is not None and scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")

    rng = np.random.default_rng(seed)
    windows = []

    for patient in PATIENTS:
        for day in range(days):
            # Windows within a day share a small day-level effect.
            day_hr_offset = float(rng.normal(0, 0.8))
            day_activity_factor = float(
                rng.lognormal(mean=0, sigma=0.12)
            )

            for slot in range(6):
                index = day * 6 + slot
                window_start = start + timedelta(hours=4 * index)
                window_end = window_start + timedelta(hours=4)

                resting_hr, steps = ordinary_measurements(
                    rng,
                    patient.id,
                    slot,
                    day_hr_offset,
                    day_activity_factor,
                )

                coverage = round(float(rng.uniform(90, 100)), 1)
                connection = ConnectionStatus.CONNECTED

                affected = patient.id == "patient-001"

                if affected and scenario == "sustained_change":
                    if index >= EVENT_WINDOW_INDEX:
                        # A deliberately visible synthetic change.
                        # This is not a clinical deterioration definition.
                        resting_hr = round(resting_hr + 16.0, 1)
                        steps = int(round(steps * 0.15))

                elif affected and scenario == "brief_exercise":
                    if index == EVENT_WINDOW_INDEX:
                        steps = int(round(steps * 3.5))
                        # Resting HR remains a resting measurement.
                        # We do not substitute an exercise pulse reading.

                elif affected and scenario == "wearable_disconnect":
                    if index >= EVENT_WINDOW_INDEX:
                        resting_hr = None
                        steps = None
                        coverage = 0.0
                        connection = ConnectionStatus.DISCONNECTED

                windows.append(
                    WearableWindow(
                        id=stable_id(
                            dataset_id,
                            patient.id,
                            window_start.isoformat(),
                        ),
                        patient_id=patient.id,
                        start=window_start,
                        end=window_end,
                        resting_hr=resting_hr,
                        steps=steps,
                        coverage_percent=coverage,
                        connection=connection,
                    )
                )

    return sorted(
        windows,
        key=lambda window: (window.end, window.patient_id),
    )


def generate_checkins(
    dataset_id: str,
    start: datetime,
    scenario: str,
) -> list[CheckIn]:
    """Only the independent patient-concern scenario has a scripted check-in."""
    if scenario != "unwell_ordinary":
        return []

    return [
        CheckIn(
            id=stable_id(dataset_id, "patient-001", "unwell-checkin"),
            patient_id="patient-001",
            timestamp=start + timedelta(
                hours=4 * (EVENT_WINDOW_INDEX + 1)
            ),
            feeling=Feeling.UNWELL,
            symptoms=("Feeling generally unwell",),
            temperature_c=None,
        )
    ]


def expected_outcome(scenario: str) -> dict:
    """Design expectations, not measured model results."""
    return {
        "persistent_trend_expected": scenario == "sustained_change",
        "patient_review_expected": scenario == "unwell_ordinary",
        "monitoring_unavailable_expected": (
            scenario == "wearable_disconnect"
        ),
    }


def write_windows(path: Path, windows: list[WearableWindow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=WINDOW_FIELDS)
        writer.writeheader()

        for window in windows:
            writer.writerow(
                {
                    "id": window.id,
                    "patient_id": window.patient_id,
                    "start": window.start.isoformat(),
                    "end": window.end.isoformat(),
                    # CSV stores None as an empty cell, never zero.
                    "resting_hr": window.resting_hr,
                    "steps": window.steps,
                    "coverage_percent": window.coverage_percent,
                    "connection": window.connection.value,
                }
            )


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def checkin_to_dict(checkin: CheckIn) -> dict:
    return {
        "id": checkin.id,
        "patient_id": checkin.patient_id,
        "timestamp": checkin.timestamp.isoformat(),
        "feeling": checkin.feeling.value,
        "symptoms": list(checkin.symptoms),
        "temperature_c": checkin.temperature_c,
    }


def write_scenario(
    root: Path,
    split: str,
    scenario: str,
    start: datetime,
    seed: int,
) -> None:
    dataset_id = f"{split}-{scenario}"
    directory = root / split / scenario

    windows = generate_windows(
        dataset_id=dataset_id,
        start=start,
        days=SCENARIO_DAYS,
        seed=seed,
        scenario=scenario,
    )

    checkins = generate_checkins(dataset_id, start, scenario)

    write_windows(directory / "windows.csv", windows)
    write_json(
        directory / "checkins.json",
        [checkin_to_dict(checkin) for checkin in checkins],
    )

    event_start = start + timedelta(hours=4 * EVENT_WINDOW_INDEX)
    first_changed_window_end = event_start + timedelta(hours=4)

    write_json(
        directory / "metadata.json",
        {
            "dataset_id": dataset_id,
            "scenario": scenario,
            "split": split,
            "seed": seed,
            "synthetic": True,
            "affected_patient_id": "patient-001",
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(days=SCENARIO_DAYS)).isoformat(),
            # State at reset: one completed ordinary window is available.
            "initial_simulated_time": (
                start + timedelta(hours=4)
            ).isoformat(),
            "event_onset": (
                first_changed_window_end.isoformat()
                if scenario == "unwell_ordinary"
                else event_start.isoformat()
            ),
            "expected": expected_outcome(scenario),
            "events": [
                {
                    "timestamp": first_changed_window_end.isoformat(),
                    "label": (
                        "Scripted unwell check-in"
                        if scenario == "unwell_ordinary"
                        else "First affected window becomes available"
                    ),
                },
                {
                    "timestamp": (
                        first_changed_window_end + timedelta(hours=4)
                    ).isoformat(),
                    "label": "Following window becomes available",
                },
            ],
        },
    )


def generate_all(root: Path = FIXTURES_DIR) -> None:
    if SETTINGS.window_hours != 4:
        raise ValueError("This generator implements four-hour windows.")

    root.mkdir(parents=True, exist_ok=True)

    write_json(
        root / "patients.json",
        [asdict(patient) for patient in PATIENTS],
    )

    reference = generate_windows(
        dataset_id="reference",
        start=REFERENCE_START,
        days=SETTINGS.reference_days,
        seed=SETTINGS.random_seed,
    )

    calibration = generate_windows(
        dataset_id="calibration",
        start=CALIBRATION_START,
        days=SETTINGS.calibration_days,
        seed=SETTINGS.random_seed + 1,
    )

    if max(window.end for window in reference) > CALIBRATION_START:
        raise ValueError("Reference and calibration periods overlap.")

    write_windows(root / "reference.csv", reference)
    write_windows(root / "calibration.csv", calibration)

    for index, scenario in enumerate(SCENARIOS):
        write_scenario(
            root=root,
            split="scenarios",
            scenario=scenario,
            start=DEMO_START,
            seed=SETTINGS.random_seed + 100 + index,
        )

        write_scenario(
            root=root,
            split="evaluation",
            scenario=scenario,
            start=EVALUATION_START,
            seed=SETTINGS.random_seed + 1000 + index,
        )

    write_json(
        root / "manifest.json",
        {
            "generator_version": 1,
            "synthetic": True,
            "reference_rows": len(reference),
            "calibration_rows": len(calibration),
            "rows_per_scenario": len(PATIENTS) * SCENARIO_DAYS * 6,
            "window_hours": 4,
            "seed": SETTINGS.random_seed,
            "notes": [
                "All identities and measurements are fictional.",
                "Empty CSV measurements mean missing, not zero.",
                "Reference and calibration represent assumed stable periods.",
                "Evaluation uses separate seeds and dates.",
                "Evaluation shares generator assumptions with demo data.",
                "Scenario expectations are not clinical labels.",
                "No clinical performance claims are supported.",
            ],
        },
    )


if __name__ == "__main__":
    generate_all()
    print(f"Synthetic fixtures written to: {FIXTURES_DIR}")