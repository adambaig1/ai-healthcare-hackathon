"""Wearable charts with fixed personal baseline comparisons."""

from datetime import timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from domain import AppState, DataQuality
from rules import window_quality, evaluate_clinical_score
from math import expm1

def build_chart_data(
    state: AppState,
    patient_id: str,
    detector=None,
) -> pd.DataFrame:
    # 1. Grab all relevant data for this patient up to the current simulated time
    windows = sorted(
        (
            window
            for window in state.windows.values()
            if window.patient_id == patient_id
            and window.end <= state.simulated_time
        ),
        key=lambda window: window.end,
    )
    
    checkins = sorted(
        (
            checkin
            for checkin in state.checkins.values()
            if checkin.patient_id == patient_id
            and checkin.timestamp <= state.simulated_time
        ),
        key=lambda c: c.timestamp,
    )
    
    assessments = sorted(
        (
            assessment
            for assessment in state.assessments.values()
            if assessment.patient_id == patient_id
            and assessment.timestamp <= state.simulated_time
        ),
        key=lambda a: a.timestamp,
    )

    columns = [
        "timestamp",
        "resting_hr",
        "steps",
        "baseline_hr",
        "baseline_steps",
        "news2_score",
    ]

    if not windows:
        return pd.DataFrame(columns=columns)

    by_end = {window.end: window for window in windows}
    by_checkin = {checkin.timestamp: checkin for checkin in checkins}

    # 2. Build a unified timeline of 4-hour window ends AND check-in times
    timestamps = list(pd.date_range(
        start=windows[0].end,
        end=state.simulated_time,
        freq="4h",
    ))
    
    for c in checkins:
        if c.timestamp not in timestamps:
            timestamps.append(c.timestamp)
            
    timestamps.sort()

    rows = []
    latest_assessment = None

    # 3. Populate the DataFrame
    for timestamp in timestamps:
        end = timestamp.to_pydatetime() if hasattr(timestamp, 'to_pydatetime') else timestamp
        window = by_end.get(end)
        checkin = by_checkin.get(end)
        
        # Keep track of the most recent AI assessment for NEWS2 combined scoring
        current_assessments = [a for a in assessments if a.timestamp <= end]
        if current_assessments:
            latest_assessment = current_assessments[-1]

        usable = (
            window is not None
            and window_quality(window, as_of=window.end) == DataQuality.AVAILABLE
        )

        baseline = None
        if detector is not None and window is not None:
            start = (end - timedelta(hours=4)).astimezone(timezone.utc)
            baseline = detector.baselines.get((patient_id, start.hour // 4))

        # Calculate NEWS2 score only at timestamps where a check-in occurred
        news2 = None
        if checkin:
            score, _ = evaluate_clinical_score(checkin=checkin, assessment=latest_assessment)
            news2 = score

        rows.append(
            {
                "timestamp": end,
                "resting_hr": window.resting_hr if usable else None,
                "steps": window.steps if usable else None,
                "baseline_hr": baseline.hr_median if baseline else None,
                "baseline_steps": expm1(baseline.log_steps_median) if baseline else None,
                "news2_score": news2,
            }
        )

    return pd.DataFrame(rows, columns=columns)


def build_trend_figure(frame: pd.DataFrame) -> go.Figure:
    figure = make_subplots(
        rows=3, 
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(
            "Resting Heart Rate",
            "Activity (Steps)",
            "Escalation Score",
        ),
    )

    # 1. Heart Rate (Actual + Baseline) - connectgaps=True bridges the missing data periods
    figure.add_trace(
        go.Scatter(x=frame["timestamp"], y=frame["resting_hr"], mode="lines+markers", name="RHR", line={"color": "#117C83", "width": 3}, connectgaps=True),
        row=1, col=1,
    )
    figure.add_trace(
        go.Scatter(x=frame["timestamp"], y=frame["baseline_hr"], mode="lines", name="Baseline RHR", line={"color": "#7C8791", "width": 2, "dash": "dash"}, connectgaps=True),
        row=1, col=1,
    )

    # 2. Steps (Actual + Baseline) - connectgaps=True bridges the missing data periods
    figure.add_trace(
        go.Scatter(x=frame["timestamp"], y=frame["steps"], mode="lines+markers", name="Steps", line={"color": "#117C83", "width": 3}, connectgaps=True),
        row=2, col=1,
    )
    figure.add_trace(
        go.Scatter(x=frame["timestamp"], y=frame["baseline_steps"], mode="lines", name="Baseline Steps", line={"color": "#7C8791", "width": 2, "dash": "dash"}, connectgaps=True),
        row=2, col=1,
    )
    
    # 3. NEWS2 Score (Plotted as distinct dots, not connected lines)
    figure.add_trace(
        go.Scatter(x=frame["timestamp"], y=frame["news2_score"], mode="markers", name="NEWS2 Score", marker={"color": "#D32F2F", "size": 10}),
        row=3, col=1,
    )
    
    # Add the Red escalation threshold line at >= 4 points
    figure.add_hline(y=4, line_dash="dot", line_color="red", annotation_text="Escalation Trigger", row=3, col=1)

    # Format Axes
    figure.update_yaxes(title_text="bpm", row=1, col=1)
    figure.update_yaxes(title_text="Steps", rangemode="tozero", row=2, col=1)
    figure.update_yaxes(title_text="Points", rangemode="tozero", row=3, col=1)
    figure.update_xaxes(title_text="Time — UTC", row=3, col=1)

    figure.update_layout(
        height=700,
        margin={"l": 20, "r": 20, "t": 40, "b": 30},
        template="plotly_white",
        showlegend=False,
        hovermode="x unified",
    )

    return figure