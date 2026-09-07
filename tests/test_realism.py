"""Tests for the process-realism evidence module."""

from safeco.realism import check_process_realism

BENIGN_IDS = (
    "benign_spike_01",
    "benign_duty_jitter_01",
    "benign_setpoint_nudge_01",
)


def test_startup_01_is_realistic():
    report = check_process_realism("startup_01")
    assert report.ok


def test_startup_01_has_required_checks():
    report = check_process_realism("startup_01")
    names = [name for name, _, _ in report.checks]
    assert "level_bounds" in names
    assert "flow_balance" in names
    assert "monotonic_timestamps" in names


def test_realism_report_is_deterministic():
    a = check_process_realism("startup_01")
    b = check_process_realism("startup_01")
    assert a.ok == b.ok
    assert a.checks == b.checks


def test_benign_scenarios_are_realistic():
    for scenario_id in BENIGN_IDS:
        report = check_process_realism(scenario_id)
        assert report.ok, f"{scenario_id} failed realism checks: " + "; ".join(
            f"{name}: {msg}" for name, ok, msg in report.checks if not ok
        )
