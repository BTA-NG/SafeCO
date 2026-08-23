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
