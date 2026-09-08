"""Process-realism evidence: assert scenario output obeys plant physics.

Realistic scenarios must never flicker state, elide a phase, or report
telemetry that contradicts the plant model. This module turns those
qualities into a machine-checkable ``RealismReport`` per scenario so the
simulator contributes evidence rather than vibes.

The checks are advisory evidence for humans, not a behaviour gate: plan
constraints are enforced by invariant violations in ``PlantSimulator.step``
and the advisory-only invariant rule (see AGENTS.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise

from .evaluation import events_for_scenario
from .scenarios import ANOMALY_PLANS, NORMAL_SCENARIOS, TELEMETRY_NOISE, run_scenario

FLOW_IN_PER_SECOND = 1.0
FLOW_OUT_PER_SECOND = 0.35
# Longest legitimate single-step swing is a 30s fill at net 0.65/s (startup_01
# enter_running). Anything beyond that implies elided physics or bad timing.
MAX_TANK_SLEW = 25.0
_FLOW_TOLERANCE = 1e-9


@dataclass
class RealismReport:
    """Outcome of running every realism check for one scenario.

    Attributes:
        scenario_id: Scenario registry key that was evaluated.
        ok: ``True`` only when every check passed.
        checks: Ordered ``(name, passed, message)`` tuples describing each
            check and, on failure, the evidence that failed it.

    """

    scenario_id: str
    ok: bool
    checks: list[tuple[str, bool, str]] = field(default_factory=list)


def check_process_realism(scenario_id: str, seed: int = 42) -> RealismReport:
    """Run every realism check against a scenario's deterministic output.

    Args:
        scenario_id: Scenario registry key. Normal and attack scenarios are
            both accepted; violation checks apply to normal scenarios only.
        seed: Deterministic simulator seed.

    Returns:
        A ``RealismReport`` whose ``ok`` flag is true when all checks pass.

    Raises:
        KeyError: If ``scenario_id`` is not a registered scenario.

    """
    observed = run_scenario(scenario_id, seed=seed)
    true = run_scenario(scenario_id, seed=seed, anomaly_plan=[])
    checks = [
        _check_level_bounds(true.snapshots),
        _check_flow_balance(true.snapshots),
        _check_valve_pump_consistency(true.snapshots),
        _check_bounded_slew(true.snapshots),
    ]
    if scenario_id in NORMAL_SCENARIOS:
        checks.append(_check_zero_violations(true.violations))
    noise_check = _check_bounded_noise(scenario_id, observed.snapshots, true.snapshots)
    if noise_check is not None:
        checks.append(noise_check)
    checks.append(_check_monotonic_timestamps(scenario_id, seed))
    return RealismReport(scenario_id, all(ok for _, ok, _ in checks), checks)


def _check_level_bounds(snapshots: list[dict]) -> tuple[str, bool, str]:
    """Assert every snapshot keeps the tank within its physical range."""
    for index, snapshot in enumerate(snapshots):
        if not 0.0 <= snapshot["tank_level"] <= 100.0:
            return (
                "level_bounds",
                False,
                f"tank_level {snapshot['tank_level']!r} out of range "
                f"at snapshot {index}",
            )
    return ("level_bounds", True, "tank_level within physical range")


def _check_flow_balance(snapshots: list[dict]) -> tuple[str, bool, str]:
    """Assert ``flow_rate`` equals ``inflow - outflow`` recomputed from state."""
    for index, snapshot in enumerate(snapshots):
        inflow = (
            FLOW_IN_PER_SECOND
            if snapshot["pump_on"] and snapshot["inlet_valve_open"]
            else 0.0
        )
        outflow = FLOW_OUT_PER_SECOND if snapshot["outlet_valve_open"] else 0.0
        expected = inflow - outflow
        if abs(snapshot["flow_rate"] - expected) > _FLOW_TOLERANCE:
            return (
                "flow_balance",
                False,
                f"flow_rate {snapshot['flow_rate']} != {expected} at snapshot {index}",
            )
    return ("flow_balance", True, "flow_rate equals inflow minus outflow")


def _check_valve_pump_consistency(
    snapshots: list[dict],
) -> tuple[str, bool, str]:
    """Assert a running pump never has its inlet valve closed."""
    for index, snapshot in enumerate(snapshots):
        if snapshot["pump_on"] and not snapshot["inlet_valve_open"]:
            return (
                "valve_pump_consistency",
                False,
                f"pump on with inlet closed at snapshot {index}",
            )
    return (
        "valve_pump_consistency",
        True,
        "pump implies inlet valve open",
    )


def _check_bounded_slew(snapshots: list[dict]) -> tuple[str, bool, str]:
    """Assert consecutive tank readings change at most ``MAX_TANK_SLEW``."""
    for index in range(1, len(snapshots)):
        slew = abs(snapshots[index]["tank_level"] - snapshots[index - 1]["tank_level"])
        if slew > MAX_TANK_SLEW:
            return (
                "bounded_slew",
                False,
                f"tank jumped {slew} between snapshots {index - 1} and {index}",
            )
    return ("bounded_slew", True, "consecutive tank deltas stay bounded")


def _check_zero_violations(violations: list[list[str]]) -> tuple[str, bool, str]:
    """Assert a normal/benign scenario triggers no invariant violations."""
    for index, step_violations in enumerate(violations):
        if step_violations:
            return (
                "zero_violations",
                False,
                f"violations {step_violations} at step {index}",
            )
    return ("zero_violations", True, "no invariant violations reported")


def _check_bounded_noise(
    scenario_id: str,
    observed: list[dict],
    true: list[dict],
) -> tuple[str, bool, str] | None:
    """Assert observed telemetry stays within the registered noise clamp.

    The check runs only for scenarios whose plan consists solely of
    ``telemetry_noise`` entries; mixed plans change step durations or
    fields in ways that make a per-step comparison invalid.

    Args:
        scenario_id: Scenario registry key used to find its anomaly plan.
        observed: Observed snapshots after benign perturbation.
        true: Unperturbed snapshots for the same scenario and seed.

    Returns:
        The check result, or ``None`` when no noise plan applies.

    """
    plan = ANOMALY_PLANS.get(scenario_id)
    if not plan:
        return None
    noise_entries = [entry for entry in plan if entry[1] == TELEMETRY_NOISE]
    if not noise_entries or len(noise_entries) != len(plan):
        return None
    clamp = max(
        params.get("clamp_sigma", 3.0) * params["noise_scale"]
        for _, _, params in noise_entries
    )
    for index, (obs, real) in enumerate(zip(observed, true, strict=True)):
        for analog_field in ("tank_level", "flow_rate"):
            deviation = abs(obs[analog_field] - real[analog_field])
            if deviation > clamp:
                return (
                    "bounded_noise",
                    False,
                    f"{analog_field} deviation {deviation} exceeds {clamp} "
                    f"at snapshot {index}",
                )
    return ("bounded_noise", True, "observed telemetry within noise clamp")


def _check_monotonic_timestamps(scenario_id: str, seed: int) -> tuple[str, bool, str]:
    """Assert event-trace timestamps never move backwards (flake guard)."""
    timestamps = [
        event.timestamp for event in events_for_scenario(scenario_id, seed).events
    ]
    pairs = list(pairwise(timestamps))
    monotonic = all(a <= b for a, b in pairs)
    backsteps = sum(a > b for a, b in pairs)
    if not monotonic:
        return (
            "monotonic_timestamps",
            False,
            f"{backsteps} timestamp backsteps over {len(timestamps)} events",
        )
    return (
        "monotonic_timestamps",
        True,
        f"{len(timestamps)} event timestamps non-decreasing",
    )
