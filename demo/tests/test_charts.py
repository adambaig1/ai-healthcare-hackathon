from datetime import timedelta

from scripts.generate_data import generate_all
from simulation import advance_to, create_demo
from views.charts import build_chart_data, build_trend_figure


def test_disconnect_is_shown_as_a_chart_gap(tmp_path):
    generate_all(tmp_path)
    controller = create_demo("wearable_disconnect", root=tmp_path)

    advance_to(
        controller,
        controller.session.scenario.end_time,
    )

    frame = build_chart_data(
        controller.session.state,
        "patient-001",
        controller.engine.detector,
    )

    assert len(frame) == 12
    assert frame["resting_hr"].iloc[:8].notna().all()
    assert frame["steps"].iloc[:8].notna().all()

    assert frame["resting_hr"].iloc[8:].isna().all()
    assert frame["steps"].iloc[8:].isna().all()

    # Fixed reference comparisons remain available during missing readings.
    assert frame["baseline_hr"].notna().all()

    figure = build_trend_figure(frame)
    assert all(trace.connectgaps is False for trace in figure.data)


def test_chart_does_not_show_future_measurements(tmp_path):
    generate_all(tmp_path)
    controller = create_demo(root=tmp_path)

    frame = build_chart_data(
        controller.session.state,
        "patient-001",
        controller.engine.detector,
    )

    assert len(frame) == 1
    assert frame["timestamp"].max() <= (
        controller.session.state.simulated_time
    )


def test_absent_window_creates_a_gap(tmp_path):
    generate_all(tmp_path)
    controller = create_demo(root=tmp_path)

    advance_to(
        controller,
        controller.session.scenario.end_time,
    )

    state = controller.session.state

    missing_end = (
        controller.session.scenario.start_time
        + timedelta(hours=12)
    )

    remove_id = next(
        window.id
        for window in state.windows.values()
        if window.patient_id == "patient-001"
        and window.end == missing_end
    )
    del state.windows[remove_id]

    frame = build_chart_data(
        state,
        "patient-001",
        controller.engine.detector,
    )

    missing_row = frame.loc[frame["timestamp"] == missing_end]

    assert len(missing_row) == 1
    assert missing_row["resting_hr"].isna().all()
    assert missing_row["steps"].isna().all()