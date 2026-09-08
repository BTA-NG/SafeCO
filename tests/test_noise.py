"""Tests for bounded telemetry noise on observed snapshot data."""

from safeco.realism import check_process_realism
from safeco.scenarios import (
    NORMAL_SCENARIOS,
    observed_state_snapshots,
    run_scenario,
    scenario_fingerprint,
)

NOISE_SCALE = 0.2
CLAMP_SIGMA = 3.0


def test_benign_noise_01_registered_as_normal():
    assert "benign_noise_01" in NORMAL_SCENARIOS
    assert run_scenario("benign_noise_01", seed=42).ground_truth == "normal"


def test_benign_noise_01_has_no_invariant_violations():
    result = run_scenario("benign_noise_01", seed=42)
    assert all(v == [] for v in result.violations)


def test_benign_noise_01_is_deterministic_from_seed():
    a = scenario_fingerprint(run_scenario("benign_noise_01", seed=42))
    b = scenario_fingerprint(run_scenario("benign_noise_01", seed=42))
    assert a == b
    assert a != scenario_fingerprint(run_scenario("benign_noise_01", seed=43))


def test_noise_is_bounded_and_centered():
    noisy = run_scenario("benign_noise_01", seed=42).snapshots
    clean = run_scenario("benign_noise_01", seed=42, anomaly_plan=[]).snapshots
    deltas = [
        s["tank_level"] - c["tank_level"] for s, c in zip(noisy, clean, strict=True)
    ]
    assert deltas
    assert all(abs(d) <= CLAMP_SIGMA * NOISE_SCALE for d in deltas)
    assert abs(sum(deltas) / len(deltas)) <= 1.0
    assert sum(d != 0 for d in deltas) >= 1


def test_flow_rate_noise_is_bounded():
    noisy = run_scenario("benign_noise_01", seed=42).snapshots
    clean = run_scenario("benign_noise_01", seed=42, anomaly_plan=[]).snapshots
    deltas = [
        s["flow_rate"] - c["flow_rate"] for s, c in zip(noisy, clean, strict=True)
    ]
    assert all(abs(d) <= CLAMP_SIGMA * NOISE_SCALE for d in deltas)


def test_benign_noise_01_passes_realism():
    report = check_process_realism("benign_noise_01")
    names = [name for name, _, _ in report.checks]
    assert "bounded_noise" in names
    assert report.ok


def test_observed_state_snapshots_match_run_scenario():
    for scenario_id in ("benign_noise_01", "benign_spike_01"):
        assert (
            observed_state_snapshots(scenario_id, seed=42)
            == run_scenario(scenario_id, seed=42).snapshots
        )
