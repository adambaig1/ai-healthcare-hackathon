import pytest
from datetime import datetime
from services import submit_checkin
from domain import AppState, Patient, Feeling

def test_submit_checkin_adds_to_state():
    state = AppState(
        simulated_time=datetime(2026, 1, 1, 12, 0, 0),
        patients={"patient-001": Patient(id="patient-001", name="Alex Morgan", baseline_id="baseline-001")}
    )
    
    submit_checkin(
        state=state,
        command_id="cmd-123",
        patient_id="patient-001",
        feeling=Feeling.MOSTLY_WELL.value,
        symptoms=("nausea",),
        temperature_c=37.2
    )
    
    assert len(state.checkins) == 1
    assert "cmd-123" in state.processed_command_ids
    
    latest = list(state.checkins.values())[0]
    assert latest.patient_id == "patient-001"
    assert latest.temperature_c == 37.2
    assert "nausea" in latest.symptoms