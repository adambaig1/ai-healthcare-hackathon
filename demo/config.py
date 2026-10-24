"""Experimental demo settings, not clinical thresholds or waiting periods."""

from dataclasses import dataclass
from pathlib import Path


APP_NAME = "Oncology Watch"

PROJECT_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = PROJECT_DIR / "fixtures"


@dataclass(frozen=True)
class DemoSettings:
    # Reproducible synthetic data and model training.
    random_seed: int = 42

    # Synthetic data periods.
    reference_days: int = 14
    calibration_days: int = 7
    window_hours: int = 4

    # Isolation Forest and calibration.
    n_estimators: int = 100
    threshold_percentile: float = 97.5

    # Persistence rule.
    consecutive_windows: int = 2

    # Provisional data-quality settings.
    min_coverage_percent: float = 80.0
    max_reading_age_hours: float = 6.0

    # Floors for median absolute deviation denominators.
    min_hr_mad_bpm: float = 2.0
    min_log_steps_mad: float = 0.25


SETTINGS = DemoSettings()