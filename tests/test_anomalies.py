"""Tests for benign-anomaly scenarios and the anomaly execution path."""

from safeco.scenarios import NORMAL_SCENARIOS, run_scenario, scenario_fingerprint


def test_empty_anomaly_plan_preserves_base_snapshots():
    NORMAL_SCENARIOS["_anom_demo"] = lambda: [("only_phase", 2.0, None)]
    try:
        base = run_scenario("_anom_demo", seed=42)
        anom = run_scenario("_anom_demo", seed=42, anomaly_plan=[])
    finally:
        del NORMAL_SCENARIOS["_anom_demo"]
    assert scenario_fingerprint(base) == scenario_fingerprint(anom)
