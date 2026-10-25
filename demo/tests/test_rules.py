import pytest
from datetime import datetime
from collections import namedtuple

class Feeling:
    WELL = 1
    MOSTLY_WELL = 2
    NOT_WELL = 3
    VERY_UNWELL = 4
    EXTREMELY_UNWELL = 5

class Symptom:
    CHILLS = "chills_or_shivering"
    NAUSEA = "nausea"

MockCheckin = namedtuple('MockCheckin', ['feeling', 'symptoms', 'temperature_c'])
MockAssessment = namedtuple('MockAssessment', ['anomaly_score'])
MockWindow = namedtuple('MockWindow', ['connection', 'coverage_percent'])

class ConnectionStatus:
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"

class DataQuality:
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"

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
    window = MockWindow(connection=ConnectionStatus.DISCONNECTED, coverage_percent=100.0)
    # window_quality takes only 1 argument
    assert window_quality(window) == DataQuality.UNAVAILABLE

def test_window_quality_low_coverage():
    from rules import window_quality
    window = MockWindow(connection=ConnectionStatus.CONNECTED, coverage_percent=40.0)
    assert window_quality(window) == DataQuality.UNAVAILABLE