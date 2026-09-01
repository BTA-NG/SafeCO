import pytest

from safeco.alerts import ReasonCode
from safeco.baseline import check_baseline, extract_features
from safeco.detector import detect
from safeco.evaluation import (
    BENIGN_EVALUATION_SCENARIOS,
    events_for_scenario,
    train_baseline_from_scenarios,
)
from safeco.events import Event, ProcessSnapshot


def _event(
    *,
    mode="running",
    command="write_coil",
    target="pump",
    value=1,
    tank_level=50.0,
    target_level=70.0,
    high_level_limit=90.0,
    sequence_id=1,
):
    return Event(
        scenario_id="baseline_unit",
        ground_truth="normal",
        source="scheduler",
        command=command,
        target=target,
        value=value,
        mode=mode,
        process=ProcessSnapshot(
            tank_level=tank_level,
            valve_state="open",
            pump_state="on" if target == "pump" and value == 1 else "off",
            inlet_valve_state="open",
            outlet_valve_state="open",
            mode=mode,
            power_source="grid",
            target_level=target_level,
            high_level_limit=high_level_limit,
        ),
        sequence_id=sequence_id,
    )


def test_extract_features_groups_by_mode_command_and_target():
    features = extract_features(_event())
    assert features.group_key == "running/write_coil/pump"
    assert features.numeric_features()["tank_level"] == 50.0


def test_baseline_training_rejects_attack_scenarios():
    with pytest.raises(ValueError, match="attack scenarios"):
        train_baseline_from_scenarios(("startup_01", "attack_drift_01"))


def test_baseline_training_is_deterministic():
    first = train_baseline_from_scenarios(("steady_running_01",))
    second = train_baseline_from_scenarios(("steady_running_01",))
    assert first == second


def test_unknown_baseline_group_does_not_alert():
    profile = train_baseline_from_scenarios(("steady_running_01",))
    event = _event(mode="shutdown", command="write_holding", target="unknown", value=10)
    assert check_baseline(event, [], profile) == []


def test_baseline_is_silent_on_benign_training_scenarios():
    profile = train_baseline_from_scenarios(BENIGN_EVALUATION_SCENARIOS)
    for scenario_id in BENIGN_EVALUATION_SCENARIOS:
        history = []
        for event in events_for_scenario(scenario_id).events:
            assert ReasonCode.BASELINE_DEVIATION not in {
                alert.reason_code
                for alert in detect(event, history, baseline_profile=profile)
            }
            history.append(event)


def test_baseline_flags_explainable_multi_feature_deviation():
    profile = train_baseline_from_scenarios(("steady_running_01",))
    history = [_event(sequence_id=i, tank_level=50.0) for i in range(1, 10)]
    event = _event(
        sequence_id=10,
        tank_level=150.0,
        target_level=99.0,
        high_level_limit=100.0,
    )

    alerts = check_baseline(event, history, profile)

    assert [alert.reason_code for alert in alerts] == [ReasonCode.BASELINE_DEVIATION]
    evidence = alerts[0].evidence
    assert evidence["baseline_group"] == "running/write_coil/pump"
    assert set(evidence["features_outside_range"]) >= {"tank_level", "target_level"}
    assert "observed" in evidence
