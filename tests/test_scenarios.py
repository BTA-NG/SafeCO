import pytest

from safeco.plant import OperatingMode, Register
from safeco.scenarios import (
    GENERATOR_VERSION,
    NORMAL_SCENARIOS,
    ScenarioResult,
    Step,
    _execute,
    run_scenario,
)


def _demo_steps() -> list[Step]:
    return [
        ("only_phase", 2.0, lambda s: s.apply_coil(Register.PUMP_COMMAND, 1)),
    ]


def test_unknown_scenario_raises_keyerror():
    with pytest.raises(KeyError):
        run_scenario("does_not_exist")


def test_execute_emits_one_snapshot_per_step_and_forwards_commands():
    NORMAL_SCENARIOS["_demo"] = _demo_steps
    try:
        snaps, cmds = [], []
        result = run_scenario("_demo", seed=42,
                              on_command=cmds.append, on_snapshot=snaps.append)
    finally:
        del NORMAL_SCENARIOS["_demo"]
    assert len(result.snapshots) == len(result.violations) == len(snaps) == 1
    assert len(result.commands) == len(cmds) == 1
    assert result.snapshots[0]["phase"] == "only_phase"
    assert isinstance(result, ScenarioResult)


def test_result_records_generator_version():
    NORMAL_SCENARIOS["_demo"] = _demo_steps
    try:
        assert run_scenario("_demo").generator_version == GENERATOR_VERSION
    finally:
        del NORMAL_SCENARIOS["_demo"]


def test_startup_scenario_reaches_running_without_violations():
    result = run_scenario("startup_01", seed=42)
    assert all(v == [] for v in result.violations)
    final = result.final_state
    assert final["mode"] == "running"
    assert final["pump_on"] is True
    levels = [s["tank_level"] for s in result.snapshots]
    assert levels[-1] > levels[0]


def test_steady_running_stays_below_high_limit():
    result = run_scenario("steady_running_01", seed=42)
    assert all("tank_above_high_level_limit" not in v for v in result.violations)
    assert len(result.snapshots) == 13  # 1 config + 6 x (drain + fill)
    assert result.final_state["tank_level"] < result.final_state["high_level_limit"]


def test_controlled_shutdown_ends_cleanly():
    result = run_scenario("controlled_shutdown_01", seed=42)
    assert all(v == [] for v in result.violations)
    final = result.final_state
    assert final["mode"] == "shutdown"
    assert final["pump_on"] is False
    assert final["inlet_valve_open"] is False


def test_grid_recovery_is_benign_and_ends_on_generator_power():
    result = run_scenario("grid_recovery_01", seed=42)
    assert all(v == [] for v in result.violations)
    final = result.final_state
    assert final["power_source"] == "generator"
    assert final["mode"] == "running"


@pytest.mark.parametrize("scenario_id", sorted(NORMAL_SCENARIOS))
def test_scenarios_are_deterministic_from_seed(scenario_id):
    a = run_scenario(scenario_id, seed=42).snapshots
    b = run_scenario(scenario_id, seed=42).snapshots
    assert a == b
