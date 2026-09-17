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
import random
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from .plant import OperatingMode, PowerSource, Register
from .simulator import CommandRecord, PlantSimulator

GENERATOR_VERSION = "safeco-scenarios/1.3"
"""Version tag recorded in every ``ScenarioResult`` for dataset provenance."""

GROUND_TRUTH: dict[str, str] = {
    "maintenance_01": "maintenance",
    "attack_injection_01": "injection",
    "attack_replay_01": "replay",
    "attack_mistimed_01": "mistimed",
    "attack_drift_01": "drift",
    "attack_baseline_low_tank_01": "baseline_anomaly",
    "attack_baseline_high_limit_01": "baseline_anomaly",
    "attack_baseline_mode_context_01": "baseline_anomaly",
    "attack_injection_jitter_01": "injection",
    "attack_replay_jitter_01": "replay",
    "attack_mistimed_jitter_01": "mistimed",
    "attack_drift_jitter_01": "drift",
}
"""Override map for ground-truth labels.

Scenarios not listed default to ``"normal"``.
"""

Step = tuple[str, float, Callable[[PlantSimulator], None] | None]
"""A single scenario step: ``(phase_name, duration_seconds, action_or_None)``."""

SENSOR_SPIKE = "sensor_spike"
DURATION_JITTER = "duration_jitter"
SETPOINT_NUDGE = "setpoint_nudge"
TELEMETRY_NOISE = "telemetry_noise"
"""Benign-anomaly kinds understood by ``_execute``."""

Anomaly = tuple[str, str, dict]
"""One benign perturbation: ``(phase_prefix, kind, params)``.

Kinds and params:

- ``sensor_spike``: ``{"match": str, "field": str, "magnitude": float,
  "holds": int}`` — perturb an observed telemetry field for a few steps.
- ``duration_jitter``: ``{"match": str, "fraction": float}`` — vary a
  step's simulated duration by up to ``fraction``.
- ``setpoint_nudge``: ``{"match": str, "delta": float, "holds": int}`` —
  offset the observed target level for a few self-correcting steps.
- ``telemetry_noise``: ``{"match": str, "noise_scale": float,
  "clamp_sigma": float}`` — add gaussian noise to observed analog fields
  on every matching step, clamped to ``clamp_sigma`` standard deviations.
"""

AnomalyPlan = list[Anomaly]
"""Ordered benign-perturbation schedule applied by the scenario executor."""


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
        step_durations: Actual simulated duration of each step, already run
            through any ``DURATION_JITTER`` perturbation. One entry per step,
            in step order.

    """

    scenario_id: str
    seed: int
    generator_version: str = GENERATOR_VERSION
    ground_truth: str = "normal"
    commands: list[CommandRecord] = field(default_factory=list)
    snapshots: list[dict] = field(default_factory=list)
    violations: list[list[str]] = field(default_factory=list)
    step_durations: list[float] = field(default_factory=list)

    @property
    def final_state(self) -> dict:
        """Return the snapshot from the last step of the scenario."""
        return self.snapshots[-1]


def scenario_fingerprint(result: ScenarioResult) -> str:
    """Compute a SHA-256 fingerprint proving seed-reproducibility.

    The fingerprint is computed over a canonical JSON representation of
    the result's metadata, commands, snapshots, and step durations. Two
    runs with the same seed and generator version always produce the
    same fingerprint.

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
        "step_durations": result.step_durations,
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
    anomaly_plan: AnomalyPlan | None = None,
) -> ScenarioResult:
    """Execute a list of steps against a fresh simulator and collect results.

    Args:
        scenario_id: Registry key for this scenario run.
        seed: Random seed forwarded to ``PlantSimulator``.
        steps: Ordered list of ``(phase, seconds, action)`` tuples.
        ground_truth: Ground-truth label for the resulting ``ScenarioResult``.
        on_command: Optional callback invoked with each ``CommandRecord``
            and the simulator's current ``PlantState`` at command time.
        on_snapshot: Optional callback invoked with each snapshot dict.
        anomaly_plan: Optional benign-perturbation schedule. ``None`` or an
            empty plan reproduces the base scenario exactly.

    Returns:
        A populated ``ScenarioResult`` containing all commands, snapshots,
        and per-step violations.

    """
    sim = PlantSimulator(seed=seed)

    def notify_command(record: CommandRecord) -> None:
        if on_command is not None:
            on_command(record, sim.state)

    sim.on_command = notify_command
    result = ScenarioResult(scenario_id, seed, ground_truth=ground_truth)
    anomaly_rng = _anomaly_rng(seed, scenario_id) if anomaly_plan else None
    counters = [0] * len(anomaly_plan or [])
    for phase, seconds, action in steps:
        step_seconds = _perturbed_duration(phase, seconds, anomaly_plan, anomaly_rng)
        result.step_durations.append(step_seconds)
        if action is not None:
            action(sim)
        result.violations.append(sim.step(step_seconds))
        snap = sim.snapshot()
        snap["phase"] = phase
        snap = _perturbed_observed(snap, phase, anomaly_plan, counters, anomaly_rng)
        result.snapshots.append(snap)
        if on_snapshot is not None:
            on_snapshot(snap)
    result.commands.extend(sim.commands)
    return result


def _anomaly_rng(seed: int, scenario_id: str) -> random.Random:
    """Return the scenario anomaly RNG, seeded to keep runs reproducible."""
    return random.Random(f"{seed}:{scenario_id}:{GENERATOR_VERSION}")


def _perturbed_duration(
    phase: str,
    seconds: float,
    plan: AnomalyPlan | None,
    rng: random.Random | None,
) -> float:
    """Return the step duration after any benign duration jitter."""
    if not plan:
        return seconds
    step_seconds = seconds
    for _, (key, kind, params) in enumerate(plan):
        if phase.startswith(key) and kind == DURATION_JITTER:
            step_seconds = _apply_duration_jitter(step_seconds, params, rng)
    return step_seconds


def _perturbed_observed(
    snapshot: dict,
    phase: str,
    plan: AnomalyPlan | None,
    counters: list[int],
    rng: random.Random | None,
) -> dict:
    """Return the observed snapshot after benign telemetry perturbations.

    Perturbations apply to a copy only; the true ``PlantState`` is never
    mutated, so invariant checks cannot trip on a sensor artifact.
    """
    if not plan:
        return snapshot
    observed = snapshot
    for index, (key, kind, params) in enumerate(plan):
        if not phase.startswith(key):
            continue
        if kind == SENSOR_SPIKE and counters[index] < params["holds"]:
            observed = _apply_sensor_spike(observed, params)
            counters[index] += 1
        elif kind == SETPOINT_NUDGE and counters[index] < params["holds"]:
            observed = _apply_setpoint_nudge(observed, params)
            counters[index] += 1
        elif kind == TELEMETRY_NOISE and rng is not None:
            observed = _apply_telemetry_noise(observed, params, rng)
    return observed


def _apply_duration_jitter(
    seconds: float,
    params: dict,
    rng: random.Random,
) -> float:
    """Return ``seconds`` varied deterministically by ``params["fraction"]``."""
    fraction = params["fraction"]
    factor = 1.0 + fraction * (2.0 * rng.random() - 1.0)
    return seconds * factor


def _apply_sensor_spike(snapshot: dict, params: dict) -> dict:
    """Return an observed-snapshot copy with telemetry spiked by magnitude."""
    field = params["field"]
    observed = dict(snapshot)
    observed[field] = observed[field] + params["magnitude"]
    return observed


def _apply_setpoint_nudge(snapshot: dict, params: dict) -> dict:
    """Return an observed-snapshot copy with the target level nudged by delta."""
    observed = dict(snapshot)
    observed["target_level"] = observed["target_level"] + params["delta"]
    return observed


def _apply_telemetry_noise(
    snapshot: dict,
    params: dict,
    rng: random.Random,
) -> dict:
    """Return an observed-snapshot copy with clamped gaussian telemetry noise.

    Noise is drawn per matching step from the scenario RNG, so the whole
    trace stays reproducible. The ``clamp_sigma`` bound keeps a single
    spurious reading inside the physical register range.
    """
    observed = dict(snapshot)
    scale = params["noise_scale"]
    clamp = params.get("clamp_sigma", 3.0) * scale
    for analog_field in ("tank_level", "flow_rate"):
        delta = rng.gauss(0.0, scale)
        while abs(delta) > clamp:
            delta = rng.gauss(0.0, scale)
        observed[analog_field] = observed[analog_field] + delta
    return observed


NORMAL_SCENARIOS: dict[str, Callable[[], list[Step]]] = {}  # filled by Tasks 5-6
ATTACK_SCENARIOS: dict[str, Callable[[], list[Step]]] = {}
"""Deterministic attack scenario registry kept separate from benign data."""


def runnable_scenarios() -> dict[str, Callable[[], list[Step]]]:
    """Return every scenario id the runner can execute.

    This is the single source of truth for "what can be run": the benign and
    attack registries plus the timing-jitter variants. ``run_scenario``, the CLI
    ``main``, and the API's scenario-detail validation all resolve ids against
    this set so a run and the validation that precedes it can never disagree.

    It is deliberately *wider* than the curated ``GET /scenarios`` picker list
    (normal + attack only): the jitter variants stay out of the picker and the
    evaluation exact-set until they are opted in, but they remain directly
    runnable by id, so the id validator must recognise them.

    Returns:
        A merged ``{id: step-factory}`` dict spanning the normal, attack, and
        jitter registries. A fresh dict each call, so callers may not mutate the
        underlying registries through it.

    """
    return {**NORMAL_SCENARIOS, **ATTACK_SCENARIOS, **ATTACK_JITTER_SCENARIOS}


def run_scenario(
    name: str,
    seed: int = 42,
    *,
    on_command=None,
    on_snapshot=None,
    anomaly_plan: AnomalyPlan | None = None,
) -> ScenarioResult:
    """Run a named scenario from the ``NORMAL_SCENARIOS`` registry.

    Args:
        name: Scenario registry key (e.g. ``"startup_01"``).
        seed: Random seed for reproducibility.
        on_command: Optional callback invoked with each ``CommandRecord``
            and the simulator's current ``PlantState`` at command time.
        on_snapshot: Optional callback invoked with each snapshot dict.
        anomaly_plan: Optional benign-perturbation schedule forwarded to
            ``_execute``.

    Returns:
        A populated ``ScenarioResult``.

    Raises:
        KeyError: If ``name`` is not found in the registry.

    """
    scenarios = runnable_scenarios()
    if name not in scenarios:
        raise KeyError(f"unknown scenario {name!r}; known: {sorted(scenarios)}")
    plans = {**ANOMALY_PLANS, **ATTACK_JITTER_PLANS}
    plan = anomaly_plan if anomaly_plan is not None else plans.get(name)
    return _execute(
        name,
        seed,
        scenarios[name](),
        ground_truth=GROUND_TRUTH.get(name, "normal"),
        on_command=on_command,
        on_snapshot=on_snapshot,
        anomaly_plan=plan,
    )


def observed_state_snapshots(scenario_id: str, seed: int = 42) -> list[dict]:
    """Return the observed snapshot series for a scenario, after perturbation.

    This is the handoff seam for the evaluation harness: it exposes exactly
    what ``run_scenario`` produced with the scenario's registered plan (noise,
    spike, jitter, or none). Joseph's ``events_for_scenario`` should map these
    observed values onto ``Event.process`` when baseline metrics must exercise
    the anomalies (the denoised ``PlantState`` values remain available via
    ``run_scenario(..., anomaly_plan=[]).snapshots``).

    Args:
        scenario_id: Scenario registry key.
        seed: Random seed for reproducibility.

    Returns:
        Observed snapshots with the registered plan applied.

    Raises:
        KeyError: If ``scenario_id`` is not a registered scenario.

    """
    return run_scenario(scenario_id, seed=seed).snapshots


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

    def enter_recovery(sim: PlantSimulator) -> None:
        sim.apply_coil(Register.PUMP_COMMAND, 0)
        sim.state.power_source = PowerSource.OFF
        sim.force_mode_command(int(OperatingMode.RECOVERY))

    def restart(sim: PlantSimulator) -> None:
        sim.apply_coil(Register.PUMP_COMMAND, 1)
        sim.apply_holding(Register.MODE_COMMAND, 2)

    return [
        ("configure_running", 1.0, _configure_running),
        ("grid_loss", 5.0, enter_recovery),
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


def attack_baseline_low_tank_steps() -> list[Step]:
    """Build baseline-only anomaly: safe pump write in unusual low-level context."""

    def unusual_context(sim: PlantSimulator) -> None:
        sim.state.tank_level = 5.0
        sim.state.target_level = 40.0
        sim.state.high_level_limit = 99.0
        sim.apply_coil(Register.PUMP_COMMAND, 1)

    return [
        ("configure_running", 1.0, _configure_running),
        ("attacker_low_tank_context", 2.0, unusual_context),
    ]


def attack_baseline_high_limit_steps() -> list[Step]:
    """Build baseline-only anomaly: safe pump stop in unusual high-limit context."""

    def unusual_context(sim: PlantSimulator) -> None:
        sim.state.tank_level = 88.0
        sim.state.target_level = 45.0
        sim.state.high_level_limit = 99.0
        sim.apply_coil(Register.PUMP_COMMAND, 0)

    return [
        ("configure_running", 1.0, _configure_running),
        ("attacker_high_limit_context", 2.0, unusual_context),
    ]


def attack_baseline_mode_context_steps() -> list[Step]:
    """Build baseline-only anomaly: normal mode write in unusual process context."""

    def unusual_context(sim: PlantSimulator) -> None:
        sim.state.tank_level = 10.0
        sim.state.target_level = 35.0
        sim.state.high_level_limit = 99.0
        sim.apply_holding(Register.MODE_COMMAND, int(OperatingMode.RUNNING))

    return [
        ("configure_running", 1.0, _configure_running),
        ("attacker_mode_context", 2.0, unusual_context),
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


def benign_spike_steps() -> list[Step]:
    """Build a sensor-spike scenario: a transient tank-level blip that recovers."""
    return [
        ("configure_running", 1.0, _configure_running),
        ("pressurize", 3.0, None),
        ("spike_a", 1.0, None),
        ("spike_b", 1.0, None),
        ("settle_c", 3.0, None),
        ("settle_d", 3.0, None),
    ]


def benign_duty_jitter_steps() -> list[Step]:
    """Build a demand scenario with slightly varied drain/fill durations."""
    steps: list[Step] = [("configure_running", 1.0, _configure_running)]
    for i in range(3):
        steps.append(
            (f"drain_{i}", 8.0, lambda s: s.apply_coil(Register.PUMP_COMMAND, 0))
        )
        steps.append(
            (f"fill_{i}", 12.0, lambda s: s.apply_coil(Register.PUMP_COMMAND, 1))
        )
    return steps


def benign_setpoint_nudge_steps() -> list[Step]:
    """Build a self-correcting setpoint scenario: an observed target blip."""
    return [
        ("configure_running", 1.0, _configure_running),
        ("nudge_a", 2.0, None),
        ("nudge_b", 2.0, None),
        ("restore_a", 2.0, None),
        ("restore_b", 2.0, None),
    ]


def benign_noise_steps() -> list[Step]:
    """Build a steady-running scenario with bounded telemetry noise."""
    steps: list[Step] = [("configure_running", 1.0, _configure_running)]
    for i in range(3):
        steps.append(
            (f"demand_drain_{i}", 8.0, lambda s: s.apply_coil(Register.PUMP_COMMAND, 0))
        )
        steps.append(
            (f"pump_fill_{i}", 12.0, lambda s: s.apply_coil(Register.PUMP_COMMAND, 1))
        )
    return steps


ANOMALY_PLANS: dict[str, AnomalyPlan] = {
    "benign_spike_01": [
        (
            "spike",
            SENSOR_SPIKE,
            {"field": "tank_level", "magnitude": 3.0, "holds": 2},
        )
    ],
    "benign_duty_jitter_01": [
        ("drain", DURATION_JITTER, {"fraction": 0.15}),
        ("fill", DURATION_JITTER, {"fraction": 0.15}),
    ],
    "benign_setpoint_nudge_01": [("nudge", SETPOINT_NUDGE, {"delta": 0.5, "holds": 1})],
    "benign_noise_01": [
        (
            "",
            TELEMETRY_NOISE,
            {"noise_scale": 0.2, "clamp_sigma": 3.0},
        )
    ],
}
"""Benign-perturbation schedule per scenario.

``run_scenario`` applies these automatically unless an explicit plan is
passed. The evaluation harness replays raw steps today, so it sees clean
traces; hook ``ANOMALY_PLANS`` there when baseline metrics must exercise
the anomalies (a Joseph/Daniel follow-up).
"""


NORMAL_SCENARIOS.update(
    {
        "benign_spike_01": benign_spike_steps,
        "benign_duty_jitter_01": benign_duty_jitter_steps,
        "benign_setpoint_nudge_01": benign_setpoint_nudge_steps,
        "benign_noise_01": benign_noise_steps,
    }
)

ATTACK_SCENARIOS.update(
    {
        "attack_injection_01": attack_injection_steps,
        "attack_replay_01": attack_replay_steps,
        "attack_mistimed_01": attack_mistimed_steps,
        "attack_drift_01": attack_drift_steps,
        "attack_baseline_low_tank_01": attack_baseline_low_tank_steps,
        "attack_baseline_high_limit_01": attack_baseline_high_limit_steps,
        "attack_baseline_mode_context_01": attack_baseline_mode_context_steps,
    }
)

ATTACK_JITTER_SCENARIOS: dict[str, Callable[[], list[Step]]] = {
    "attack_injection_jitter_01": attack_injection_steps,
    "attack_replay_jitter_01": attack_replay_steps,
    "attack_mistimed_jitter_01": attack_mistimed_steps,
    "attack_drift_jitter_01": attack_drift_steps,
}
"""Timing-jitter attack variants.

Each entry reuses the base attack's step factory; ``ATTACK_JITTER_PLANS``
varies the duration of approach phases so the unsafe command lands at a
different, still-reproducible offset. Kept separate from ``ATTACK_SCENARIOS``
so Joseph's exact-set assertion and eval id->reason mapping stay valid until
he opts the variants in.
"""

ATTACK_JITTER_PLANS: dict[str, AnomalyPlan] = {
    "attack_injection_jitter_01": [
        ("initial_shutdown", DURATION_JITTER, {"fraction": 0.6})
    ],
    "attack_replay_jitter_01": [
        ("close_inlet_for_service", DURATION_JITTER, {"fraction": 0.6})
    ],
    "attack_mistimed_jitter_01": [
        ("force_recovery_without_power", DURATION_JITTER, {"fraction": 0.6})
    ],
    "attack_drift_jitter_01": [
        ("attacker_raise_target", DURATION_JITTER, {"fraction": 0.6})
    ],
}
"""Jitter plan per timing-variation variant (see ``ATTACK_JITTER_SCENARIOS``)."""


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
    scenarios = runnable_scenarios()
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
