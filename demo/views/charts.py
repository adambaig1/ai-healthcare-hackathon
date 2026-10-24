"""Wearable charts with fixed personal baseline comparisons."""

from datetime import timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from domain import AppState, DataQuality
from rules import window_quality

from math import expm1

def build_chart_data(
    state: AppState,
    patient_id: str,
    detector=None,
) -> pd.DataFrame:
    windows = sorted(
        (
            window
            for window in state.windows.values()
            if window.patient_id == patient_id
            and window.end <= state.simulated_time
        ),
        key=lambda window: window.end,
    )

    columns = [
        "timestamp",
        "resting_hr",
        "steps",
        "baseline_hr",
        "baseline_steps",
    ]

    if not windows:
        return pd.DataFrame(columns=columns)

    by_end = {window.end: window for window in windows}

    # Include absent four-hour windows so charts show gaps rather
    # than connecting measurements across missing periods.
    timestamps = pd.date_range(
        start=windows[0].end,
        end=state.simulated_time,
        freq="4h",
    )

    rows = []

    for timestamp in timestamps:
        end = timestamp.to_pydatetime()
        window = by_end.get(end)

        usable = (
            window is not None
            and window_quality(
                window,
                as_of=window.end,
            ) == DataQuality.AVAILABLE
        )

        baseline = None

        if detector is not None:
            start = (end - timedelta(hours=4)).astimezone(timezone.utc)
            baseline = detector.baselines.get(
                (patient_id, start.hour // 4)
            )

        rows.append(
            {
                "timestamp": end,
                "resting_hr": window.resting_hr if usable else None,
                "steps": window.steps if usable else None,
                "baseline_hr": (
                    baseline.hr_median if baseline else None
                ),
                "baseline_steps": (
                    expm1(baseline.log_steps_median)
                    if baseline
                    else None
                ),
            }
        )

    return pd.DataFrame(rows, columns=columns)


def build_trend_figure(frame: pd.DataFrame) -> go.Figure:
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.14,
        subplot_titles=(
            "Resting heart rate",
            "Activity per four-hour window",
        ),
    )

    for row, actual, baseline, unit in (
        (1, "resting_hr", "baseline_hr", "bpm"),
        (2, "steps", "baseline_steps", "steps"),
    ):
        figure.add_trace(
            go.Scatter(
                x=frame["timestamp"],
                y=frame[actual],
                mode="lines+markers",
                name="Observed",
                legendgroup="observed",
                showlegend=row == 1,
                line={"color": "#117C83", "width": 3},
                marker={"size": 6},
                connectgaps=False,
                hovertemplate=(
                    "%{x|%d %b %H:%M} UTC"
                    f"<br>%{{y:.1f}} {unit}<extra></extra>"
                ),
            ),
            row=row,
            col=1,
        )

        figure.add_trace(
            go.Scatter(
                x=frame["timestamp"],
                y=frame[baseline],
                mode="lines",
                name="Personal baseline",
                legendgroup="baseline",
                showlegend=row == 1,
                line={
                    "color": "#7C8791",
                    "width": 2,
                    "dash": "dash",
                },
                connectgaps=False,
                hovertemplate=(
                    "%{x|%d %b %H:%M} UTC"
                    f"<br>Baseline: %{{y:.1f}} {unit}<extra></extra>"
                ),
            ),
            row=row,
            col=1,
        )

    figure.update_yaxes(title_text="bpm", row=1, col=1)
    figure.update_yaxes(title_text="Steps", rangemode="tozero", row=2, col=1)
    figure.update_xaxes(title_text="Window end — UTC", row=2, col=1)

    figure.update_layout(
        height=560,
        margin={"l": 20, "r": 20, "t": 60, "b": 30},
        template="plotly_white",
        legend={"orientation": "h", "y": 1.12, "x": 0},
        hovermode="x unified",
    )

    return figure