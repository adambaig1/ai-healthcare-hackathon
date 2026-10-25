import pytest
from datetime import datetime, timezone
from collections import namedtuple
from domain import ConnectionStatus, DataQuality

class Feeling:
    WELL = 1
    MOSTLY_WELL = 2
    NOT_WELL = 3
    VERY_UNWELL = 4
    EXTREMELY_UNWELL = 5

MockCheckin = namedtuple('MockCheckin', ['feeling', 'symptoms', 'temperature_c'])
MockWindow = namedtuple('MockWindow', ['connection', 'coverage_percent', 'end', 'resting_hr', 'steps'])

def test_sos_trigger_score():
    from rules import evaluate_clinical_score
    checkin = MockCheckin(feeling=Feeling.EXTREMELY_UNWELL, symptoms=[], temperature_c=37.0)
    score, reasons = evaluate_clinical_score(checkin, None)
    
    assert score >= 4, "SOS button must immediately trigger NEWS2 threshold (>= 4)"
    assert any("Extremely Unwell" in r for r in reasons), "SOS reason must be logged for the Nurse Dashboard"

def test_healthy_patient_score():
    from rules import evaluate_clinical_score
    checkin = MockCheckin(feeling=Feeling.WELL, symptoms=[], temperature_c=36.5)
    score, reasons = evaluate_clinical_score(checkin, None)
    
    assert score == 0, "Healthy patient should have a score of 0"
    assert len(reasons) == 0

def test_window_quality_down():
    from rules import window_quality
    window = MockWindow(
        connection=ConnectionStatus.DISCONNECTED, 
        coverage_percent=100.0, 
        end=datetime.now(timezone.utc),
        resting_hr=60,
        steps=100
    )
    assert window_quality(window, as_of=datetime.now(timezone.utc)) == DataQuality.DISCONNECTED

def test_window_quality_low_coverage():
    from rules import window_quality
    window = MockWindow(
        connection=ConnectionStatus.CONNECTED, 
        coverage_percent=40.0, 
        end=datetime.now(timezone.utc),
        resting_hr=60,
        steps=100
    )
    # Since low coverage is rejected, we assert it is simply NOT marked as available
    assert window_quality(window, as_of=datetime.now(timezone.utc)) != DataQuality.AVAILABLE