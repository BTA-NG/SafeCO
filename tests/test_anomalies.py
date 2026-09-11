"""Tests for benign-anomaly scenarios and the anomaly execution path."""

import random

from safeco.scenarios import (
    NORMAL_SCENARIOS,
    _apply_duration_jitter,
    _apply_sensor_spike,
    run_scenario,
    scenario_fingerprint,
)


def test_empty_anomaly_plan_preserves_base_snapshots():
    NORMAL_SCENARIOS["_anom_demo"] = lambda: [("only_phase", 2.0, None)]
    try:
        base = run_scenario("_anom_demo", seed=42)
        anom = run_scenario("_anom_demo", seed=42, anomaly_plan=[])
    finally:
        del NORMAL_SCENARIOS["_anom_demo"]
    assert scenario_fingerprint(base) == scenario_fingerprint(anom)


def _spike_demo_steps():
    return [
        ("pressurize", 1.0, None),
        ("spike_one", 1.0, None),
        ("spike_two", 1.0, None),
        ("settle", 1.0, None),
    ]


def test_duration_jitter_is_deterministic_and_bounded():
    rng = random.Random(7)
    draws = [_apply_duration_jitter(10.0, {"fraction": 0.1}, rng) for _ in range(50)]
    assert all(9.0 <= draw <= 11.0 for draw in draws)
    second_rng = random.Random(7)
    second = [
        _apply_duration_jitter(10.0, {"fraction": 0.1}, second_rng) for _ in range(50)
    ]
    assert draws == second


def test_sensor_spike_applies_to_observed_copy_only():
    snapshot = {"tank_level": 50.0, "flow_rate": 1.0, "phase": "spike"}
    observed = _apply_sensor_spike(snapshot, {"field": "tank_level", "magnitude": 5.0})
    assert observed is not snapshot
    assert observed["tank_level"] == 55.0
    assert snapshot["tank_level"] == 50.0
    assert observed["flow_rate"] == 1.0


def test_sensor_spike_perturbs_observed_and_recovers():
    NORMAL_SCENARIOS["_spike_demo"] = _spike_demo_steps
    try:
        base = run_scenario("_spike_demo", seed=42).snapshots
        plan = [
            (
                "spike",
                "sensor_spike",
                {"field": "tank_level", "magnitude": 5.0, "holds": 1},
            )
        ]
        anom = run_scenario("_spike_demo", seed=42, anomaly_plan=plan).snapshots
    finally:
        del NORMAL_SCENARIOS["_spike_demo"]
    assert anom[1]["tank_level"] == base[1]["tank_level"] + 5.0
    assert anom[2]["tank_level"] == base[2]["tank_level"]
    assert anom[3]["tank_level"] == base[3]["tank_level"]


BENIGN_ANOMALY_SCENARIOS = (
    "benign_spike_01",
    "benign_duty_jitter_01",
    "benign_setpoint_nudge_01",
)


def test_benign_anomaly_scenarios_are_registered_as_normal():
    assert set(BENIGN_ANOMALY_SCENARIOS) <= set(NORMAL_SCENARIOS)
    for scenario_id in BENIGN_ANOMALY_SCENARIOS:
        assert run_scenario(scenario_id, seed=42).ground_truth == "normal"


def test_benign_anomaly_scenarios_have_no_invariant_violations():
    for scenario_id in BENIGN_ANOMALY_SCENARIOS:
        result = run_scenario(scenario_id, seed=42)
        assert all(v == [] for v in result.violations)


def test_benign_anomaly_scenarios_are_deterministic_from_seed():
    for scenario_id in BENIGN_ANOMALY_SCENARIOS:
        a = scenario_fingerprint(run_scenario(scenario_id, seed=42))
        b = scenario_fingerprint(run_scenario(scenario_id, seed=42))
        assert a == b
        assert a != scenario_fingerprint(run_scenario(scenario_id, seed=43))


def test_spike_is_visible_in_observed_data_and_self_restores():
    base = run_scenario("benign_spike_01", seed=42, anomaly_plan=[]).snapshots
    anom = run_scenario("benign_spike_01", seed=42).snapshots
    deviations = [
        s["tank_level"] - b["tank_level"]
        for b, s in zip(base, anom, strict=True)
        if s["tank_level"] != b["tank_level"]
    ]
    assert deviations
    assert all(deviation > 0 for deviation in deviations)
    assert anom[-1]["tank_level"] == base[-1]["tank_level"]


def test_setpoint_nudge_self_corrects():
    base = run_scenario("benign_setpoint_nudge_01", seed=42, anomaly_plan=[]).snapshots
    anom = run_scenario("benign_setpoint_nudge_01", seed=42).snapshots
    base_targets = [s["target_level"] for s in base]
    anom_targets = [s["target_level"] for s in anom]
    assert any(t != b for t, b in zip(anom_targets, base_targets, strict=True))
    assert anom_targets[-1] == base_targets[-1] == 70.0


def test_generator_version_includes_1_3():
    from safeco.scenarios import GENERATOR_VERSION

    assert "1.3" in GENERATOR_VERSION
