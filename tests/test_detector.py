import pytest

from safeco.alerts import SEVERITY_RANK, ReasonCode, Severity
from safeco.collector import plant_snapshot
from safeco.detector import (
    LEGAL_TRANSITIONS,
    check_rate_and_drift,
    check_invariants,
    check_replay,
    check_transitions,
    detect,
)
from safeco.events import Event, ProcessSnapshot
from safeco.plant import OperatingMode, PlantState, PowerSource
from safeco.scenarios import NORMAL_SCENARIOS, run_scenario

BENIGN_SCENARIOS = sorted(NORMAL_SCENARIOS)

VALIDATE_TO_REASON = {
    "pump_running_with_inlet_closed": ReasonCode.UNSAFE_PUMP_START,
    "pump_running_without_power": ReasonCode.PUMP_WITHOUT_POWER,
    "tank_above_high_level_limit": ReasonCode.TANK_ABOVE_HIGH_LIMIT,
    "target_not_below_high_limit": ReasonCode.SETPOINT_AT_OR_ABOVE_LIMIT,
    "tank_level_out_of_physical_range": ReasonCode.LEVEL_OUT_OF_RANGE,
}


def _event(
    *,
    mode="running",
    tank_level=50.0,
    valve_state="open",
    pump_state="off",
    inlet_valve_state="open",
    outlet_valve_state="open",
    power_source="grid",
    target_level=70.0,
    high_level_limit=90.0,
    source="scheduler",
    ground_truth="normal",
    scenario_id="unit_01",
    sequence_id=1,
    command="write_coil",
    target="pump",
    value=1,
    timestamp=None,
    raw=None,
):
    kwargs = {}
    if timestamp is not None:
        kwargs["timestamp"] = timestamp
    return Event(
        scenario_id=scenario_id,
        ground_truth=ground_truth,
        source=source,
        command=command,
        target=target,
        value=value,
        mode=mode,
        process=ProcessSnapshot(
            tank_level=tank_level,
            valve_state=valve_state,
            pump_state=pump_state,
            inlet_valve_state=inlet_valve_state,
            outlet_valve_state=outlet_valve_state,
            mode=mode,
            power_source=power_source,
            target_level=target_level,
            high_level_limit=high_level_limit,
        ),
        sequence_id=sequence_id,
        raw=raw or {},
        **kwargs,
    )


def _event_from_snapshot(snap, scenario_id, sequence_id, ground_truth="normal"):
    # Scenario snapshots are the richest benign data available today, so the
    # detector is exercised against them rather than against hand-built states.
    return Event(
        scenario_id=scenario_id,
        ground_truth=ground_truth,
        source="scheduler",
        command="telemetry",
        target="plant",
        value=None,
        mode=snap["mode"],
        process=ProcessSnapshot(
            tank_level=snap["tank_level"],
            valve_state="open" if snap["inlet_valve_open"] else "closed",
            pump_state="on" if snap["pump_on"] else "off",
            inlet_valve_state="open" if snap["inlet_valve_open"] else "closed",
            outlet_valve_state="open" if snap["outlet_valve_open"] else "closed",
            mode=snap["mode"],
            power_source=snap["power_source"],
            target_level=snap["target_level"],
            high_level_limit=snap["high_level_limit"],
        ),
        sequence_id=sequence_id,
    )


def _codes(alerts):
    return {alert.reason_code for alert in alerts}


def _actionable(alerts):
    low = SEVERITY_RANK[Severity.LOW]
    return [a for a in alerts if SEVERITY_RANK[a.severity] > low]


# --- Layer 1: safety invariants ------------------------------------------


def test_healthy_running_event_produces_no_alerts():
    assert detect(_event(pump_state="on")) == []


def test_pump_with_inlet_closed_is_a_high_severity_contextual_alert():
    alerts = detect(_event(pump_state="on", inlet_valve_state="closed"))
    assert _codes(alerts) == {ReasonCode.UNSAFE_PUMP_START}
    alert = alerts[0]
    assert alert.severity is Severity.HIGH
    assert "inlet valve is closed" in alert.explanation
    assert alert.recommended_action
    assert alert.evidence["inlet_valve_state"] == "closed"


def test_inlet_state_falls_back_to_the_contract_alias():
    # A minimal contract event expresses the inlet through valve_state only.
    alerts = detect(
        _event(pump_state="on", valve_state="closed", inlet_valve_state="unknown")
    )
    assert _codes(alerts) == {ReasonCode.UNSAFE_PUMP_START}


def test_pump_without_power_is_flagged():
    alerts = detect(_event(pump_state="on", power_source="off"))
    assert _codes(alerts) == {ReasonCode.PUMP_WITHOUT_POWER}
    assert alerts[0].severity is Severity.HIGH


def test_tank_above_high_limit_is_critical():
    alerts = detect(_event(pump_state="on", tank_level=95.0))
    assert _codes(alerts) == {ReasonCode.TANK_ABOVE_HIGH_LIMIT}
    assert alerts[0].severity is Severity.CRITICAL
    assert "95.00%" in alerts[0].explanation


def test_tank_above_high_limit_only_applies_in_running_mode():
    # PlantState.validate scopes this invariant to RUNNING; so does Layer 1.
    assert detect(_event(mode="maintenance", tank_level=95.0)) == []


def test_setpoint_at_or_above_limit_is_flagged():
    alerts = detect(_event(target_level=90.0))
    assert _codes(alerts) == {ReasonCode.SETPOINT_AT_OR_ABOVE_LIMIT}
    assert alerts[0].severity is Severity.HIGH


def test_non_physical_level_is_reported_as_a_sensor_fault():
    alerts = detect(_event(mode="shutdown", tank_level=150.0))
    assert _codes(alerts) == {ReasonCode.LEVEL_OUT_OF_RANGE}
    assert alerts[0].severity is Severity.MEDIUM


def test_non_physical_level_does_not_suppress_the_high_limit_check():
    # Otherwise a forged out-of-range reading downgrades a critical finding.
    alerts = detect(_event(tank_level=150.0))
    assert _codes(alerts) == {
        ReasonCode.LEVEL_OUT_OF_RANGE,
        ReasonCode.TANK_ABOVE_HIGH_LIMIT,
    }


# --- Unknown context is not safe context ---------------------------------


def test_unknown_power_source_with_pump_on_reports_insufficient_context():
    alerts = detect(_event(pump_state="on", power_source="unknown"))
    assert _codes(alerts) == {ReasonCode.INSUFFICIENT_CONTEXT}
    alert = alerts[0]
    assert alert.severity is Severity.LOW
    assert alert.evidence["missing_fields"] == ["power_source"]
    assert "power_source" in alert.explanation
    assert "not confirmed safe" in alert.explanation


def test_unknown_inlet_state_is_not_reported_when_the_pump_is_off():
    # Nothing was blocked, so nothing is claimed to be missing.
    assert detect(_event(valve_state="unknown", inlet_valve_state="unknown")) == []


def test_missing_setpoint_context_names_both_fields():
    alerts = detect(_event(target_level=None, high_level_limit=None))
    assert _codes(alerts) == {ReasonCode.INSUFFICIENT_CONTEXT}
    assert alerts[0].evidence["missing_fields"] == [
        "high_level_limit",
        "target_level",
    ]


def test_both_layers_blocked_produce_one_merged_context_alert():
    history = [_event(mode="recovery", pump_state="off", power_source="off")]
    event = _event(mode="recovery", pump_state="?", high_level_limit=None)
    alerts = detect(event, history)
    context = [a for a in alerts if a.reason_code == ReasonCode.INSUFFICIENT_CONTEXT]
    assert len(context) == 1
    assert context[0].evidence["missing_fields"] == ["high_level_limit", "pump_state"]


def test_unknown_power_after_recovery_reports_insufficient_context():
    history = [_event(mode="recovery", pump_state="off", power_source="off")]
    event = _event(mode="startup", pump_state="off", power_source="unknown")
    alerts = check_transitions(event, history)
    assert _codes(alerts) == {ReasonCode.INSUFFICIENT_CONTEXT}
    assert alerts[0].evidence["missing_fields"] == ["power_source"]


# --- Layer 2: state transitions ------------------------------------------


def test_illegal_mode_transition_is_flagged():
    history = [_event(mode="shutdown", pump_state="off")]
    alerts = detect(_event(mode="maintenance", pump_state="off"), history)
    assert _codes(alerts) == {ReasonCode.ILLEGAL_MODE_TRANSITION}
    alert = alerts[0]
    assert alert.severity is Severity.HIGH
    assert alert.confidence == 0.8
    assert alert.evidence["previous_mode"] == "shutdown"
    assert alert.evidence["previous_event_id"] == history[-1].event_id


@pytest.mark.parametrize(("previous", "current"), sorted(LEGAL_TRANSITIONS))
def test_every_legal_transition_is_silent(previous, current):
    history = [_event(mode=previous, pump_state="off", power_source="generator")]
    event = _event(mode=current, pump_state="off", power_source="generator")
    assert check_transitions(event, history) == []


def test_no_history_produces_no_transition_alert():
    assert check_transitions(_event(mode="maintenance", pump_state="off")) == []


def test_unchanged_mode_produces_no_transition_alert():
    history = [_event(mode="running", pump_state="on")]
    assert check_transitions(_event(mode="running", pump_state="on"), history) == []


def test_leaving_recovery_without_power_is_out_of_sequence():
    history = [_event(mode="recovery", pump_state="off", power_source="off")]
    event = _event(mode="startup", pump_state="off", power_source="off")
    alerts = check_transitions(event, history)
    assert _codes(alerts) == {ReasonCode.RECOVERY_OUT_OF_SEQUENCE}
    assert alerts[0].severity is Severity.HIGH


def test_pump_running_during_recovery_is_flagged():
    event = _event(mode="recovery", pump_state="on", power_source="generator")
    alerts = check_transitions(event)
    assert _codes(alerts) == {ReasonCode.PUMP_ACTIVE_DURING_RECOVERY}
    assert alerts[0].severity is Severity.HIGH


# --- Layer 3: replay and sequence checks ---------------------------------


def test_duplicate_sequence_id_is_flagged():
    history = [_event(sequence_id=4)]
    alerts = check_replay(_event(sequence_id=4), history)
    assert _codes(alerts) == {ReasonCode.DUPLICATE_SEQUENCE_ID}
    assert alerts[0].severity is Severity.MEDIUM


def test_timestamp_moving_backwards_is_flagged():
    history = [
        _event(
            sequence_id=1,
            value=0,
            timestamp="2026-08-28T10:00:00+00:00",
        )
    ]
    event = _event(sequence_id=2, timestamp="2026-08-28T09:59:59+00:00")
    alerts = check_replay(event, history)
    assert _codes(alerts) == {ReasonCode.STALE_TIMESTAMP}
    assert alerts[0].evidence["previous_timestamp"] == history[-1].timestamp


def test_repeated_command_after_context_change_is_replay_suspect():
    original = _event(
        sequence_id=1,
        command="write_coil",
        target="pump",
        value=1,
        pump_state="on",
        inlet_valve_state="open",
        raw={"address": 0, "kind": "coil"},
    )
    context_change = _event(
        sequence_id=2,
        command="write_coil",
        target="inlet_valve",
        value=0,
        pump_state="off",
        inlet_valve_state="closed",
        raw={"address": 1, "kind": "coil"},
    )
    replay = _event(
        sequence_id=3,
        command="write_coil",
        target="pump",
        value=1,
        pump_state="on",
        inlet_valve_state="closed",
        raw={"address": 0, "kind": "coil"},
    )
    alerts = check_replay(replay, [original, context_change])
    assert _codes(alerts) == {ReasonCode.COMMAND_REPLAY}
    assert alerts[0].evidence["previous_event_id"] == original.event_id


def test_immediate_repeated_command_in_same_context_is_not_replay():
    original = _event(
        sequence_id=1,
        command="write_coil",
        target="pump",
        value=1,
        pump_state="on",
        raw={"address": 0, "kind": "coil"},
    )
    repeat = _event(
        sequence_id=2,
        command="write_coil",
        target="pump",
        value=1,
        pump_state="on",
        raw={"address": 0, "kind": "coil"},
    )
    assert check_replay(repeat, [original]) == []


# --- Layer 4: rate and drift checks --------------------------------------


def test_command_rate_spike_is_flagged_for_repeated_actuator_writes():
    history = [
        _event(sequence_id=i, target="pump", value=i % 2)
        for i in range(1, 7)
    ]
    event = _event(sequence_id=7, target="pump", value=1)
    alerts = check_rate_and_drift(event, history)
    assert _codes(alerts) == {ReasonCode.COMMAND_RATE_SPIKE}
    assert alerts[0].evidence["command_count"] == 7


def test_slow_setpoint_drift_is_flagged_outside_maintenance():
    history = [
        _event(
            sequence_id=i,
            command="write_holding",
            target="level_setpoint",
            value=70.0 + i,
            target_level=70.0 + i,
        )
        for i in range(1, 5)
    ]
    event = _event(
        sequence_id=5,
        command="write_holding",
        target="level_setpoint",
        value=75.5,
        target_level=75.5,
    )
    alerts = check_rate_and_drift(event, history)
    assert _codes(alerts) == {ReasonCode.SETPOINT_DRIFT}
    assert alerts[0].severity is Severity.HIGH


def test_maintenance_setpoint_changes_are_not_drift_alerts():
    history = [
        _event(
            mode="maintenance",
            sequence_id=i,
            command="write_holding",
            target="level_setpoint",
            value=70.0 + i,
            target_level=70.0 + i,
            ground_truth="maintenance",
        )
        for i in range(1, 5)
    ]
    event = _event(
        mode="maintenance",
        sequence_id=5,
        command="write_holding",
        target="level_setpoint",
        value=75.5,
        target_level=75.5,
        ground_truth="maintenance",
    )
    assert check_rate_and_drift(event, history) == []


# --- Contract and composition guarantees ---------------------------------


def test_ground_truth_and_source_are_never_detection_inputs():
    baseline = None
    for source in ("scheduler", "operator", "attacker"):
        for label in ("normal", "injection", "replay", "mistimed", "drift"):
            alerts = detect(
                _event(
                    pump_state="on",
                    inlet_valve_state="closed",
                    source=source,
                    ground_truth=label,
                )
            )
            fingerprint = [
                (a.reason_code, a.severity, a.title, a.explanation, a.confidence)
                for a in alerts
            ]
            if baseline is None:
                baseline = fingerprint
            assert fingerprint == baseline
    assert baseline


def test_evidence_carries_labels_for_the_engineer():
    alerts = detect(
        _event(
            pump_state="on",
            inlet_valve_state="closed",
            source="attacker",
            ground_truth="injection",
        )
    )
    assert alerts[0].evidence["source"] == "attacker"
    assert alerts[0].evidence["ground_truth"] == "injection"


def test_alerts_are_ordered_most_urgent_first():
    alerts = detect(
        _event(
            pump_state="on",
            inlet_valve_state="closed",
            tank_level=95.0,
            target_level=None,
        )
    )
    assert [a.severity for a in alerts] == [
        Severity.CRITICAL,
        Severity.HIGH,
        Severity.LOW,
    ]


def test_alert_ids_are_unique_per_event():
    alerts = detect(
        _event(pump_state="on", inlet_valve_state="closed", tank_level=150.0)
    )
    ids = [a.alert_id for a in alerts]
    assert len(ids) == len(set(ids))


def test_detect_is_deterministic():
    event = _event(pump_state="on", inlet_valve_state="closed")
    first = [a.canonical_json() for a in detect(event)]
    second = [a.canonical_json() for a in detect(event)]
    assert first == second


# --- Agreement with the frozen plant contract ----------------------------


@pytest.mark.parametrize(
    "plant",
    [
        PlantState(mode=OperatingMode.RUNNING, inlet_valve_open=True, pump_on=True),
        PlantState(pump_on=True, inlet_valve_open=False),
        PlantState(pump_on=True, inlet_valve_open=True, power_source=PowerSource.OFF),
        PlantState(mode=OperatingMode.RUNNING, tank_level=95.0, inlet_valve_open=True),
        PlantState(target_level=95.0, inlet_valve_open=True),
        PlantState(mode=OperatingMode.RUNNING, tank_level=150.0, inlet_valve_open=True),
    ],
)
def test_layer_one_agrees_with_plant_state_validate(plant):
    # Layer 1 restates PlantState.validate over ProcessSnapshot because the
    # detector runs on replayed events where no PlantState exists. This test
    # is what stops the two copies from drifting apart.
    event = _event_from_snapshot(plant_snapshot(plant), "contract_01", 1)
    expected = {VALIDATE_TO_REASON[name] for name in plant.validate()}
    observed = _codes(check_invariants(event)) - {ReasonCode.INSUFFICIENT_CONTEXT}
    assert observed == expected


# --- The zero-false-positive gate ----------------------------------------


def test_legal_transitions_cover_every_benign_scenario():
    observed: set[tuple[str, str]] = set()
    for scenario_id in BENIGN_SCENARIOS:
        previous = None
        for snap in run_scenario(scenario_id, seed=42).snapshots:
            if previous is not None and previous != snap["mode"]:
                observed.add((previous, snap["mode"]))
            previous = snap["mode"]
    unlisted = observed - LEGAL_TRANSITIONS
    assert not unlisted, f"benign scenarios produced unlisted transitions: {unlisted}"


@pytest.mark.parametrize("scenario_id", BENIGN_SCENARIOS)
def test_benign_scenarios_raise_no_actionable_alerts(scenario_id):
    result = run_scenario(scenario_id, seed=42)
    history: list[Event] = []
    raised = []
    for sequence_id, snap in enumerate(result.snapshots, start=1):
        event = _event_from_snapshot(
            snap, scenario_id, sequence_id, result.ground_truth
        )
        raised.extend(_actionable(detect(event, history)))
        history.append(event)
    assert raised == [], [
        (a.reason_code, a.evidence["sequence_id"], a.explanation) for a in raised
    ]


@pytest.mark.parametrize("scenario_id", BENIGN_SCENARIOS)
def test_benign_scenarios_never_lack_context(scenario_id):
    # Collector-shaped events always carry full context, so the unknown-field
    # path must stay silent on benign data.
    result = run_scenario(scenario_id, seed=42)
    for sequence_id, snap in enumerate(result.snapshots, start=1):
        event = _event_from_snapshot(snap, scenario_id, sequence_id)
        assert ReasonCode.INSUFFICIENT_CONTEXT not in _codes(detect(event))
