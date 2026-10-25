"""Generate reproducible synthetic fixtures for the 28-day narrative demo."""

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
    Symptom,
    Patient,
    WearableWindow,
)

PATIENTS = (
    Patient("patient-001", "Alex Morgan", "baseline-001"),
    Patient("patient-002", "Sam Taylor", "baseline-002"),
    Patient("patient-003", "Jamie Ellis", "baseline-003"),
)

PROFILES = {
    "patient-001": (70.0, 1.0),
    "patient-002": (77.0, 0.7),
    "patient-003": (64.0, 1.3),
}

HR_SLOT_OFFSETS = (-4.0, -3.0, 1.0, 2.0, 1.0, -1.0)
STEP_SLOT_CENTRES = (15, 80, 1000, 1500, 1100, 250)

# Only generate the winning narrative
SCENARIOS = ("golden_path",)
SCENARIO_DAYS = 28
EVENT_START_DAY = 14

REFERENCE_START = datetime(2026, 9, 1, tzinfo=timezone.utc)
CALIBRATION_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
DEMO_START = datetime(2026, 10, 24, tzinfo=timezone.utc)
EVALUATION_START = datetime(2026, 11, 1, tzinfo=timezone.utc)

WINDOW_FIELDS = [
    "id", "patient_id", "start", "end", "resting_hr", 
    "steps", "coverage_percent", "connection"
]

def stable_id(*parts: object) -> str:
    key = "|".join(str(part) for part in parts)
    return str(uuid5(NAMESPACE_URL, f"oncology-watch|{key}"))

def ordinary_measurements(rng, patient_id, slot, day_hr_offset, day_activity_factor):
    hr_centre, activity_multiplier = PROFILES[patient_id]
    resting_hr = hr_centre + HR_SLOT_OFFSETS[slot] + day_hr_offset + rng.normal(0, 1.8)
    steps = STEP_SLOT_CENTRES[slot] * activity_multiplier * day_activity_factor * rng.lognormal(mean=0, sigma=0.25)
    return round(float(resting_hr), 1), max(0, int(round(steps)))

def generate_windows(dataset_id: str, start: datetime, days: int, seed: int) -> list[WearableWindow]:
    rng = np.random.default_rng(seed)
    windows = []

    for patient in PATIENTS:
        for day in range(days):
            day_hr_offset = float(rng.normal(0, 0.8))
            day_activity_factor = float(rng.lognormal(mean=0, sigma=0.12))

            for slot in range(6):
                index = day * 6 + slot
                window_start = start + timedelta(hours=4 * index)
                window_end = window_start + timedelta(hours=4)

                resting_hr, steps = ordinary_measurements(
                    rng, patient.id, slot, day_hr_offset, day_activity_factor
                )

                # Inject the 28-day narrative for our primary patient
                if patient.id == "patient-001" and days == SCENARIO_DAYS:
                    if 14 <= day < 21:  # Week 3: Deterioration
                        resting_hr = round(resting_hr + 18.0, 1)
                        steps = int(round(steps * 0.15))

                windows.append(
                    WearableWindow(
                        id=stable_id(dataset_id, patient.id, window_start.isoformat()),
                        patient_id=patient.id,
                        start=window_start,
                        end=window_end,
                        resting_hr=resting_hr,
                        steps=steps,
                        coverage_percent=round(float(rng.uniform(90, 100)), 1),
                        connection=ConnectionStatus.CONNECTED,
                    )
                )

    return sorted(windows, key=lambda window: (window.end, window.patient_id))

def generate_checkins(dataset_id: str, start: datetime) -> list[CheckIn]:
    checkins = []
    
    # 28 days of daily check-ins for the demo patient
    for day in range(SCENARIO_DAYS):
        checkin_time = start + timedelta(days=day, hours=10)
        
        if 14 <= day < 21:  # Week 3: Deterioration
            feeling = Feeling.VERY_UNWELL
            symptoms = (Symptom.CHILLS.value, Symptom.FATIGUE.value)
            temp = round(float(np.random.default_rng().uniform(38.1, 38.6)), 1)
        else:  # Weeks 1, 2, and 4: Normal/Recovered
            feeling = Feeling.MOSTLY_WELL
            symptoms = ()
            temp = round(float(np.random.default_rng().uniform(36.5, 37.2)), 1)

        checkins.append(
            CheckIn(
                id=stable_id(dataset_id, "patient-001", f"checkin-{day}"),
                patient_id="patient-001",
                timestamp=checkin_time,
                feeling=feeling,
                symptoms=symptoms,
                temperature_c=temp,
            )
        )
    return checkins

def write_windows(path: Path, windows: list[WearableWindow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=WINDOW_FIELDS)
        writer.writeheader()
        for window in windows:
            writer.writerow({
                "id": window.id, "patient_id": window.patient_id,
                "start": window.start.isoformat(), "end": window.end.isoformat(),
                "resting_hr": window.resting_hr, "steps": window.steps,
                "coverage_percent": window.coverage_percent,
                "connection": window.connection.value,
            })

def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")

def checkin_to_dict(checkin: CheckIn) -> dict:
    return {
        "id": checkin.id, "patient_id": checkin.patient_id,
        "timestamp": checkin.timestamp.isoformat(), "feeling": checkin.feeling.value,
        "symptoms": list(checkin.symptoms), "temperature_c": checkin.temperature_c,
    }

def write_scenario(root: Path, split: str, start: datetime, seed: int) -> None:
    dataset_id = f"{split}-golden_path"
    directory = root / split / "golden_path"

    windows = generate_windows(dataset_id, start, SCENARIO_DAYS, seed)
    checkins = generate_checkins(dataset_id, start)

    write_windows(directory / "windows.csv", windows)
    write_json(directory / "checkins.json", [checkin_to_dict(c) for c in checkins])

    event_start = start + timedelta(days=EVENT_START_DAY)

    write_json(
        directory / "metadata.json",
        {
            "dataset_id": dataset_id,
            "scenario": "golden_path",
            "split": split,
            "seed": seed,
            "synthetic": True,
            "affected_patient_id": "patient-001",
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(days=SCENARIO_DAYS)).isoformat(),
            "initial_simulated_time": (start + timedelta(hours=4)).isoformat(),
            "event_onset": event_start.isoformat(),
            "expected": {"patient_review_expected": True},
            "events": [
                {
                    "timestamp": (event_start + timedelta(hours=4)).isoformat(),
                    "label": "Deterioration metrics trigger AI flag",
                }
            ],
        },
    )

def generate_all(root: Path = FIXTURES_DIR) -> None:
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "patients.json", [asdict(patient) for patient in PATIENTS])

    reference = generate_windows("reference", REFERENCE_START, SETTINGS.reference_days, SETTINGS.random_seed)
    calibration = generate_windows("calibration", CALIBRATION_START, SETTINGS.calibration_days, SETTINGS.random_seed + 1)

    write_windows(root / "reference.csv", reference)
    write_windows(root / "calibration.csv", calibration)

    write_scenario(root, "scenarios", DEMO_START, SETTINGS.random_seed + 100)
    write_scenario(root, "evaluation", EVALUATION_START, SETTINGS.random_seed + 1000)

    write_json(
        root / "manifest.json",
        {
            "generator_version": 2, "synthetic": True,
            "reference_rows": len(reference), "calibration_rows": len(calibration),
            "rows_per_scenario": len(PATIENTS) * SCENARIO_DAYS * 6,
            "notes": ["Exclusive 28-day narrative dataset generated."],
        },
    )

if __name__ == "__main__":
    generate_all()
    print(f"Narrative fixtures written to: {FIXTURES_DIR}")