"""Train once and inspect demo scores.

Run:
    python -m scripts.inspect_model

This is an engineering inspection, not clinical evaluation.
"""

from data import create_session, load_scenario, SCENARIO_NAMES
from detector import train_detector


def main() -> None:
    session = create_session()

    detector = train_detector(
        session.reference,
        session.calibration,
    )

    print("Synthetic model inspection")
    print(f"Reference windows: {detector.reference_count}")
    print(f"Calibration windows: {detector.calibration_count}")
    print(f"Patient/time-slot baselines: {len(detector.baselines)}")
    print(f"Calibrated threshold: {detector.threshold:.4f}")

    for scenario_name in SCENARIO_NAMES:
        scenario = load_scenario(scenario_name)

        print(f"\nSCENARIO: {scenario_name}")

        for window in scenario.windows:
            if window.patient_id != "patient-001":
                continue

            timestamp = window.end.strftime("%d %b %H:%M")

            try:
                result = detector.score(
                    window,
                    as_of=window.end,
                )
            except ValueError as error:
                print(f"{timestamp} | NOT SCORED | {error}")
                continue

            direction_matches = (
                result.hr_above_baseline
                and result.activity_below_baseline
            )

            print(
                f"{timestamp}"
                f" | score={result.anomaly_score:.4f}"
                f" | unusual={result.is_anomalous}"
                f" | higher-HR/lower-activity={direction_matches}"
            )


if __name__ == "__main__":
    main()