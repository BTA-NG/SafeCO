"""Deterministic scenario runner for the Adupe Municipal Water Station.

Provides a registry of named normal-operation scenarios, each defined as
a sequence of timed steps. Every scenario is fully reproducible from a
seed: the same seed always produces the same command log and snapshot
sequence. A SHA-256 fingerprint can be computed to prove reproducibility
across separate runs.

Usage::

    from safeco.scenarios import run_scenario
    result = run_scenario("startup_01", seed=42)
    print(result.final_state)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from .plant import OperatingMode, PowerSource, Register
from .simulator import CommandRecord, PlantSimulator

GENERATOR_VERSION = "safeco-scenarios/1.1"
"""Version tag recorded in every ``ScenarioResult`` for dataset provenance."""

GROUND_TRUTH: dict[str, str] = {
    "maintenance_01": "maintenance",
    "attack_injection_01": "injection",
    "attack_replay_01": "replay",
    "attack_mistimed_01": "mistimed",
    "attack_drift_01": "drift",
}
"""Override map for ground-truth labels.

Scenarios not listed default to ``"normal"``.
"""

Step = tuple[str, float, Callable[[PlantSimulator], None] | None]
"""A single scenario step: ``(phase_name, duration_seconds, action_or_None)``."""


@dataclass
class ScenarioResult:
    """Complete output of a deterministic scenario run.

    Attributes:
        scenario_id: Registry key of the scenario that was executed.
        seed: Random seed used for this run.
        generator_version: Provenance tag for the dataset.
        ground_truth: Human-readable ground-truth label (e.g. ``"normal"``,
            ``"maintenance"``).
        commands: Every command applied to the simulator during the run,
            in chronological order.
        snapshots: One ``dict`` per step, containing plant state values
            and the step's ``phase`` name.
        violations: Per-step lists of invariant violations returned by
            ``PlantSimulator.step``.

    """

    scenario_id: str
    seed: int
    generator_version: str = GENERATOR_VERSION
    ground_truth: str = "normal"
    commands: list[CommandRecord] = field(default_factory=list)
    snapshots: list[dict] = field(default_factory=list)
    violations: list[list[str]] = field(default_factory=list)

    @property
    def final_state(self) -> dict:
        """Return the snapshot from the last step of the scenario."""
        return self.snapshots[-1]


def scenario_fingerprint(result: ScenarioResult) -> str:
    """Compute a SHA-256 fingerprint proving seed-reproducibility.

    The fingerprint is computed over a canonical JSON representation of
    the result's metadata, commands, and snapshots. Two runs with the
    same seed and generator version always produce the same fingerprint.

    Args:
        result: A completed ``ScenarioResult`` to fingerprint.

    Returns:
        Lowercase hex-encoded SHA-256 digest (64 characters).

    """
    payload = {
        "scenario_id": result.scenario_id,
        "seed": result.seed,
        "generator_version": result.generator_version,
        "ground_truth": result.ground_truth,
        "commands": [asdict(c) for c in result.commands],
        "snapshots": result.snapshots,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _configure_running(sim: PlantSimulator) -> None:
    """Configure the simulator into RUNNING mode with all valves and pump open."""
    sim.apply_coil(Register.INLET_VALVE_COMMAND, 1)
    sim.apply_coil(Register.OUTLET_VALVE_COMMAND, 1)
    sim.apply_coil(Register.PUMP_COMMAND, 1)
    sim.apply_holding(Register.MODE_COMMAND, 2)  # RUNNING


def _execute(
    scenario_id: str,
    seed: int,
    steps: list[Step],
    *,
    ground_truth: str = "normal",
    on_command=None,
    on_snapshot=None,
) -> ScenarioResult:
    """Execute a list of steps against a fresh simulator and collect results.

    Args:
        scenario_id: Registry key for this scenario run.
        seed: Random seed forwarded to ``PlantSimulator``.
        steps: Ordered list of ``(phase, seconds, action)`` tuples.
        ground_truth: Ground-truth label for the resulting ``ScenarioResult``.
        on_command: Optional callback invoked with each ``CommandRecord``.
        on_snapshot: Optional callback invoked with each snapshot dict.

    Returns:
        A populated ``ScenarioResult`` containing all commands, snapshots,
        and per-step violations.

    """
    sim = PlantSimulator(seed=seed)
    sim.on_command = on_command
    result = ScenarioResult(scenario_id, seed, ground_truth=ground_truth)
    for phase, seconds, action in steps:
        if action is not None:
            action(sim)
        result.violations.append(sim.step(seconds))
        snap = sim.snapshot()
        snap["phase"] = phase
        result.snapshots.append(snap)
        if on_snapshot is not None:
            on_snapshot(snap)
    result.commands.extend(sim.commands)
    return result


NORMAL_SCENARIOS: dict[str, Callable[[], list[Step]]] = {}  # filled by Tasks 5-6
ATTACK_SCENARIOS: dict[str, Callable[[], list[Step]]] = {}
"""Deterministic attack scenario registry kept separate from benign data."""


def run_scenario(
    name: str, seed: int = 42, *, on_command=None, on_snapshot=None
) -> ScenarioResult:
    """Run a named scenario from the ``NORMAL_SCENARIOS`` registry.

    Args:
        name: Scenario registry key (e.g. ``"startup_01"``).
        seed: Random seed for reproducibility.
        on_command: Optional callback invoked with each ``CommandRecord``.
        on_snapshot: Optional callback invoked with each snapshot dict.

    Returns:
        A populated ``ScenarioResult``.

    Raises:
        KeyError: If ``name`` is not found in the registry.

    """
    scenarios = {**NORMAL_SCENARIOS, **ATTACK_SCENARIOS}
    if name not in scenarios:
        raise KeyError(f"unknown scenario {name!r}; known: {sorted(scenarios)}")
    return _execute(
        name,
        seed,
        scenarios[name](),
        ground_truth=GROUND_TRUTH.get(name, "normal"),
        on_command=on_command,
        on_snapshot=on_snapshot,
    )


def startup_steps() -> list[Step]:
    """Build the startup scenario: SHUTDOWN -> inlet open -> pump on -> RUNNING."""
    return [
        ("initial_shutdown", 1.0, None),
        ("open_inlet", 1.0, lambda s: s.apply_coil(Register.INLET_VALVE_COMMAND, 1)),
        ("start_pump", 5.0, lambda s: s.apply_coil(Register.PUMP_COMMAND, 1)),
        ("enter_running", 30.0, lambda s: s.apply_holding(Register.MODE_COMMAND, 2)),
    ]


def steady_running_steps() -> list[Step]:
    """Build the steady-running scenario: 6 demand drain/fill duty cycles."""
    steps: list[Step] = [("configure_running", 1.0, _configure_running)]
    for i in range(6):
        steps.append(
            (f"demand_drain_{i}", 8.0, lambda s: s.apply_coil(Register.PUMP_COMMAND, 0))
        )
        steps.append(
            (f"pump_fill_{i}", 12.0, lambda s: s.apply_coil(Register.PUMP_COMMAND, 1))
        )
    return steps


def controlled_shutdown_steps() -> list[Step]:
    """Build the controlled-shutdown scenario.

    Pump off -> inlet close -> demand drain -> SHUTDOWN.
    """
    return [
        ("configure_running", 1.0, _configure_running),
        ("stop_pump", 2.0, lambda s: s.apply_coil(Register.PUMP_COMMAND, 0)),
        ("close_inlet", 2.0, lambda s: s.apply_coil(Register.INLET_VALVE_COMMAND, 0)),
        ("drain_via_demand", 10.0, None),
        ("enter_shutdown", 1.0, lambda s: s.apply_holding(Register.MODE_COMMAND, 0)),
    ]


def maintenance_steps() -> list[Step]:
    """Build the maintenance scenario.

    Authorised setpoint changes at a rate-limited cadence. Five +1%
    TARGET_LEVEL raises (7000 -> 7500 raw) followed by five restore
    steps, each at 5-second intervals. The slow cadence serves as the
    benign contrast case for the drift attack in Phase 3.
    """
    steps: list[Step] = [("configure_running", 1.0, _configure_running)]
    steps.append(
        ("enter_maintenance", 2.0, lambda s: s.apply_holding(Register.MODE_COMMAND, 3))
    )
    for i in range(1, 6):
        target = 7000 + i * 100
        steps.append(
            (
                f"raise_target_{i}",
                5.0,
                lambda s, t=target: s.apply_holding(Register.TARGET_LEVEL, t),
            )
        )
    for i in range(1, 6):
        target = 7500 - i * 100
        steps.append(
            (
                f"restore_target_{i}",
                5.0,
                lambda s, t=target: s.apply_holding(Register.TARGET_LEVEL, t),
            )
        )
    steps.append(
        ("exit_maintenance", 2.0, lambda s: s.apply_holding(Register.MODE_COMMAND, 2))
    )
    steps.append(("settle_running", 2.0, None))
    return steps


def extended_normal_steps() -> list[Step]:
    """Build the extended-normal scenario: ~16 minutes of demand variation.

    Three repetitions of three demand blocks (A: 14s drain / 6s fill,
    B: 8s / 8s, C: 18s / 10s), with a benign outlet-valve service
    cycle inserted after the second repetition. Total duration ~969
    simulated seconds, level bounded between 42% and 81%.
    """
    steps: list[Step] = [("configure_running", 1.0, _configure_running)]
    for rep in range(3):
        for drain_s, fill_s in [
            (14.0, 6.0),
            (8.0, 8.0),
            (18.0, 10.0),
        ]:
            for i in range(5):
                tag = f"{rep}_{int(drain_s)}_{i}"
                steps.append(
                    (
                        f"drain_{tag}",
                        drain_s,
                        lambda s: s.apply_coil(Register.PUMP_COMMAND, 0),
                    )
                )
                steps.append(
                    (
                        f"fill_{tag}",
                        fill_s,
                        lambda s: s.apply_coil(Register.PUMP_COMMAND, 1),
                    )
                )
        if rep == 1:
            steps.append(
                (
                    "outlet_service_close",
                    4.0,
                    lambda s: s.apply_coil(Register.OUTLET_VALVE_COMMAND, 0),
                )
            )
            steps.append(
                (
                    "outlet_service_reopen",
                    4.0,
                    lambda s: s.apply_coil(Register.OUTLET_VALVE_COMMAND, 1),
                )
            )
    return steps


def grid_recovery_steps() -> list[Step]:
    """Build the grid-recovery scenario: grid loss -> generator transfer -> RUNNING."""

    def restart(sim: PlantSimulator) -> None:
        sim.apply_coil(Register.PUMP_COMMAND, 1)
        sim.apply_holding(Register.MODE_COMMAND, 2)

    return [
        ("configure_running", 1.0, _configure_running),
        ("grid_loss", 5.0, lambda s: s.state.begin_grid_recovery()),
        ("transfer_to_generator", 3.0, lambda s: s.state.transfer_to_generator()),
        ("resume_after_recovery", 5.0, lambda s: s.state.resume_after_recovery()),
        ("restart_and_run", 10.0, restart),
    ]


def attack_injection_steps() -> list[Step]:
    """Build command-injection attack: pump started with inlet path closed."""
    return [
        ("initial_shutdown", 1.0, None),
        (
            "attacker_start_pump_closed_inlet",
            2.0,
            lambda s: s.apply_coil(Register.PUMP_COMMAND, 1),
        ),
    ]


def attack_replay_steps() -> list[Step]:
    """Build replay attack: old pump-start repeated after context changed."""
    return [
        ("configure_running", 1.0, _configure_running),
        ("normal_stop_pump", 2.0, lambda s: s.apply_coil(Register.PUMP_COMMAND, 0)),
        (
            "close_inlet_for_service",
            2.0,
            lambda s: s.apply_coil(Register.INLET_VALVE_COMMAND, 0),
        ),
        (
            "attacker_replay_start_pump",
            2.0,
            lambda s: s.apply_coil(Register.PUMP_COMMAND, 1),
        ),
    ]


def attack_mistimed_steps() -> list[Step]:
    """Build mistimed command attack: plant resumes before power restoration."""

    def force_recovery_without_power(sim: PlantSimulator) -> None:
        sim.apply_coil(Register.PUMP_COMMAND, 0)
        sim.state.power_source = PowerSource.OFF
        sim.force_mode_command(int(OperatingMode.RECOVERY))

    return [
        ("configure_running", 1.0, _configure_running),
        ("force_recovery_without_power", 2.0, force_recovery_without_power),
        (
            "attacker_force_startup_without_power",
            2.0,
            lambda s: s.force_mode_command(int(OperatingMode.STARTUP)),
        ),
    ]


def attack_drift_steps() -> list[Step]:
    """Build slow setpoint drift attack outside maintenance mode."""
    steps: list[Step] = [("configure_running", 1.0, _configure_running)]
    for i in range(1, 7):
        target = 7000 + i * 100
        steps.append(
            (
                f"attacker_raise_target_{i}",
                3.0,
                lambda s, t=target: s.apply_holding(Register.TARGET_LEVEL, t),
            )
        )
    return steps


NORMAL_SCENARIOS.update(
    {
        "startup_01": startup_steps,
        "steady_running_01": steady_running_steps,
    }
)

NORMAL_SCENARIOS.update(
    {
        "controlled_shutdown_01": controlled_shutdown_steps,
        "grid_recovery_01": grid_recovery_steps,
        "maintenance_01": maintenance_steps,
        "extended_normal_01": extended_normal_steps,
    }
)

ATTACK_SCENARIOS.update(
    {
        "attack_injection_01": attack_injection_steps,
        "attack_replay_01": attack_replay_steps,
        "attack_mistimed_01": attack_mistimed_steps,
        "attack_drift_01": attack_drift_steps,
    }
)


def main(argv: list[str] | None = None) -> None:
    """Run a scenario from the command line and print JSON output.

    Args:
        argv: Argument list. Defaults to ``sys.argv[1:]`` when ``None``.

    Raises:
        SystemExit: With code 1 if the scenario name is unknown.

    """
    parser = argparse.ArgumentParser(
        description="Run a deterministic SafeCO scenario",
    )
    parser.add_argument("name", help="scenario id (see NORMAL_SCENARIOS)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fingerprint", action="store_true")
    args = parser.parse_args(argv)
    scenarios = {**NORMAL_SCENARIOS, **ATTACK_SCENARIOS}
    if args.name not in scenarios:
        print(
            f"error: unknown scenario {args.name!r}; known: {sorted(scenarios)}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    steps_factory = scenarios[args.name]
    duration_s = sum(s for _, s, _ in steps_factory())
    result = run_scenario(args.name, seed=args.seed)
    output: dict = {
        "scenario_id": result.scenario_id,
        "seed": result.seed,
        "ground_truth": result.ground_truth,
        "command_count": len(result.commands),
        "duration_s": duration_s,
        "final_state": result.final_state,
    }
    if args.fingerprint:
        output["fingerprint"] = scenario_fingerprint(result)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
