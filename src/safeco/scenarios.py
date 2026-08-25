from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from .plant import Register
from .simulator import CommandRecord, PlantSimulator

GENERATOR_VERSION = "safeco-scenarios/1.1"

GROUND_TRUTH: dict[str, str] = {
    "maintenance_01": "maintenance",
}

Step = tuple[str, float, Callable[[PlantSimulator], None] | None]


@dataclass
class ScenarioResult:
    scenario_id: str
    seed: int
    generator_version: str = GENERATOR_VERSION
    ground_truth: str = "normal"
    commands: list[CommandRecord] = field(default_factory=list)
    snapshots: list[dict] = field(default_factory=list)
    violations: list[list[str]] = field(default_factory=list)

    @property
    def final_state(self) -> dict:
        return self.snapshots[-1]


def scenario_fingerprint(result: ScenarioResult) -> str:
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


def run_scenario(
    name: str, seed: int = 42, *, on_command=None, on_snapshot=None
) -> ScenarioResult:
    if name not in NORMAL_SCENARIOS:
        raise KeyError(f"unknown scenario {name!r}; known: {sorted(NORMAL_SCENARIOS)}")
    return _execute(
        name,
        seed,
        NORMAL_SCENARIOS[name](),
        ground_truth=GROUND_TRUTH.get(name, "normal"),
        on_command=on_command,
        on_snapshot=on_snapshot,
    )


def startup_steps() -> list[Step]:
    return [
        ("initial_shutdown", 1.0, None),
        ("open_inlet", 1.0, lambda s: s.apply_coil(Register.INLET_VALVE_COMMAND, 1)),
        ("start_pump", 5.0, lambda s: s.apply_coil(Register.PUMP_COMMAND, 1)),
        ("enter_running", 30.0, lambda s: s.apply_holding(Register.MODE_COMMAND, 2)),
    ]


def steady_running_steps() -> list[Step]:
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
    return [
        ("configure_running", 1.0, _configure_running),
        ("stop_pump", 2.0, lambda s: s.apply_coil(Register.PUMP_COMMAND, 0)),
        ("close_inlet", 2.0, lambda s: s.apply_coil(Register.INLET_VALVE_COMMAND, 0)),
        ("drain_via_demand", 10.0, None),
        ("enter_shutdown", 1.0, lambda s: s.apply_holding(Register.MODE_COMMAND, 0)),
    ]


def maintenance_steps() -> list[Step]:
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
