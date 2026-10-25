import pytest
from datetime import datetime
from domain import AppState, Patient

def test_app_state_initialization():
    state = AppState(
        simulated_time=datetime.now(),
        patients={
            "patient-001": Patient(id="patient-001", name="Alex Morgan", baseline_id="baseline-001")
        }
    )
    
    assert "patient-001" in state.patients
    assert len(state.checkins) == 0
    assert len(state.windows) == 0
    assert len(state.reviews) == 0
    assert len(state.assessments) == 0
    assert len(state.audit_events) == 0