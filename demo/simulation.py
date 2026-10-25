"""Chronological demo playback, independent of Streamlit."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from config import FIXTURES_DIR
from data import DemoSession, create_session
from domain import require_aware
from monitoring import AnalysisEngine, assess_window, initialise_engine
from services import command_key, submit_checkin


@dataclass
class DemoController:
    session: DemoSession
    engine: AnalysisEngine


def create_demo(
    scenario_name: str = "golden_path", 
    root: Path = FIXTURES_DIR,
) -> DemoController:
    """Create a fresh session and process its initial completed events."""
    session = create_session(scenario_name, root)
    engine = initialise_engine(session)

    controller = DemoController(
        session=session,
        engine=engine,
    )

    advance_to(
        controller,
        session.state.simulated_time,
    )

    return controller


def advance_to(
    controller: DemoController,
    target: datetime,
) -> None:
    """Process every due event in chronological order."""
    require_aware(target)

    session = controller.session
    state = session.state
    scenario = session.scenario

    if target < state.simulated_time:
        raise ValueError("Cannot move simulated time backwards.")

    if target > scenario.end_time:
        raise ValueError("Target exceeds the scenario end.")

    events = []

    for window in scenario.windows:
        if (
            window.end <= target
            and window.id not in state.processed_window_ids
        ):
            # Priority 0: wearable windows before check-ins at equal times.
            events.append((window.end, 0, window.id, window))

    for checkin in scenario.checkins:
        command_id = f"scripted-checkin:{checkin.id}"
        key = command_key("submit_checkin", command_id)

        if (
            checkin.timestamp <= target
            and key not in state.processed_command_ids
        ):
            events.append((checkin.timestamp, 1, checkin.id, checkin))

    events.sort(key=lambda event: event[:3])

    # Detect an inconsistent runtime before partially advancing it.
    if any(
        timestamp < state.simulated_time
        for timestamp, _, _, _ in events
    ):
        raise ValueError("An unprocessed event is behind the current clock.")

    for timestamp, priority, _, record in events:
        if priority == 0:
            assess_window(
                state,
                controller.engine,
                record,
                as_of=timestamp,
            )
        else:
            # Submission services timestamp records using simulated time.
            state.simulated_time = timestamp

            submit_checkin(
                state,
                command_id=f"scripted-checkin:{record.id}",
                patient_id=record.patient_id,
                feeling=record.feeling,
                symptoms=record.symptoms,
                temperature_c=record.temperature_c,
                checkin_id=record.id,
            )

    # A target can fall between measurements or beyond the last event.
    state.simulated_time = target


def advance_one_day(controller: DemoController) -> None:
    state = controller.session.state

    target = min(
        state.simulated_time + timedelta(hours=24), # Changed to 24 hours
        controller.session.scenario.end_time,
    )

    advance_to(controller, target)


def next_event_time(controller: DemoController) -> datetime | None:
    """Find the next authored demo marker, check-in or scenario end."""
    session = controller.session
    now = session.state.simulated_time

    candidates = {
        *session.scenario.event_times,
        *(checkin.timestamp for checkin in session.scenario.checkins),
        session.scenario.end_time,
    }

    future = [timestamp for timestamp in candidates if timestamp > now]

    return min(future) if future else None


def run_to_next_event(controller: DemoController) -> None:
    target = next_event_time(controller)

    if target is not None:
        advance_to(controller, target)