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
from .scenarios import NORMAL_SCENARIOS, run_scenario

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
    result = run_scenario(scenario_id, seed=seed)
    checks = [
        _check_level_bounds(result.snapshots),
        _check_flow_balance(result.snapshots),
        _check_valve_pump_consistency(result.snapshots),
        _check_bounded_slew(result.snapshots),
    ]
    if scenario_id in NORMAL_SCENARIOS:
        checks.append(_check_zero_violations(result.violations))
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
