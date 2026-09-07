"""Layered, explainable detector for unsafe commands in Adupe events.

Layers are implemented in the order fixed by ``team_handoff.md``:

1. **Safety invariants** (``check_invariants``) — states that are unsafe
   regardless of how the plant reached them.
2. **State-transition validation** (``check_transitions``) — commands that
   are individually valid but wrong for the current operating sequence.

Replay, rate/drift, and statistical baselines are later layers and are
deliberately absent from this module.

Every layer is a pure function of the shared ``Event`` contract, so the
detector produces identical output on a live feed and on events replayed
out of SQLite. Two rules constrain all of them:

* ``Event.ground_truth`` and ``Event.source`` are evaluation metadata.
  They are never read by detection logic — only copied into evidence for
  the engineer. Branching on either would leak labels and invalidate
  every metric computed afterwards.
* **Unknown context is not safe context.** A check whose inputs are
  unavailable does not silently pass. It contributes to a single
  low-severity ``INSUFFICIENT_CONTEXT`` alert naming the fields it
  needed, so SafeCO always says what it could not evaluate.

SafeCO is advisory. Nothing in this module blocks, reverses, or delays a
command; the detector only describes what it observed.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from .alerts import (
    SEVERITY_RANK,
    Alert,
    ReasonCode,
    Severity,
    build_alert,
)
from .events import Event, ProcessSnapshot

UNKNOWN = "unknown"
"""Sentinel used by ``ProcessSnapshot`` for fields the collector did not fill."""

PUMP_STATES = frozenset({"on", "off"})
VALVE_STATES = frozenset({"open", "closed"})
POWER_SOURCES = frozenset({"off", "grid", "generator"})
WRITE_COMMANDS = frozenset({"write_coil", "write_holding", "write_register"})
SETPOINT_TARGETS = frozenset({"level_setpoint", "high_level_limit"})

PHYSICAL_LEVEL_RANGE = (0.0, 100.0)
"""Physically possible tank level, mirroring ``PlantState.validate``."""

REPLAY_CONTEXT_WINDOW = 2
"""Minimum later events before a repeated command can be treated as replay."""

RATE_WINDOW_EVENTS = 10
"""History window used by the rate checker."""

RATE_MAX_WRITES_PER_TARGET = 6
"""Maximum repeated writes to one non-setpoint target in ``RATE_WINDOW_EVENTS``."""

SETPOINT_DRIFT_WINDOW_EVENTS = 8
"""History window used by the drift checker."""

SETPOINT_DRIFT_LIMIT_PERCENT = 4.0
"""Allowed cumulative setpoint movement outside maintenance mode."""

LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("shutdown", "running"),
        ("running", "shutdown"),
        ("running", "recovery"),
        ("recovery", "startup"),
        ("startup", "running"),
        ("running", "maintenance"),
        ("maintenance", "running"),
    }
)
"""Operating-mode edges observed across the benign scenario set.

Derived empirically from the six normal scenarios registered in
``safeco.scenarios`` at generator version ``safeco-scenarios/1.1``, not
from a textbook state machine. ``startup_01``, for example, goes directly
from ``shutdown`` to ``running`` without passing through ``startup``, so
an idealised ``shutdown -> startup -> running`` table would raise a false
positive on a scenario labelled normal.

``tests/test_detector.py`` re-derives this set from the live scenario
registry and fails if a benign scenario ever produces an edge that is not
listed here. When Mahoraga adds scenarios, that test fails loudly instead
of the detector quietly producing false positives.
"""


def _event_evidence(event: Event) -> dict[str, Any]:
    """Return the event context copied into every alert's evidence.

    ``source`` and ``ground_truth`` appear here for the engineer reading
    the alert and for offline evaluation. They are never inputs to a
    detection branch.

    Args:
        event: The event under evaluation.

    Returns:
        A new dict of context values safe to embed in an alert.

    """
    return {
        "scenario_id": event.scenario_id,
        "sequence_id": event.sequence_id,
        "timestamp": event.timestamp,
        "command": event.command,
        "target": event.target,
        "value": event.value,
        "mode": event.mode,
        "source": event.source,
        "ground_truth": event.ground_truth,
    }


def _resolve_inlet_state(process: ProcessSnapshot) -> str:
    """Return the inlet valve state, falling back to the contract alias.

    ``valve_state`` is the original frozen contract field and the
    collector fills it from the inlet valve. ``inlet_valve_state`` is the
    later additive field. Minimal events carrying only the published
    contract therefore express the inlet through ``valve_state``, so the
    alias is consulted whenever the explicit field is unknown.

    Args:
        process: The event's process snapshot.

    Returns:
        ``"open"``, ``"closed"``, or ``"unknown"``.

    """
    if process.inlet_valve_state != UNKNOWN:
        return process.inlet_valve_state
    return process.valve_state


def _insufficient_context(event: Event, missing: Sequence[str]) -> Alert:
    """Build the single low-severity alert for checks that could not run.

    Args:
        event: The event under evaluation.
        missing: Names of process fields whose absence blocked a check.

    Returns:
        An ``INSUFFICIENT_CONTEXT`` alert naming the blocked fields.

    """
    fields = sorted(set(missing))
    evidence = {
        **_event_evidence(event),
        "missing_fields": fields,
        "missing_fields_text": ", ".join(fields),
    }
    return build_alert(event.event_id, ReasonCode.INSUFFICIENT_CONTEXT, evidence)


def check_invariants(event: Event) -> list[Alert]:
    """Evaluate Layer 1 safety invariants against one event.

    These mirror ``PlantState.validate`` but are expressed over
    ``ProcessSnapshot`` rather than a live ``PlantState``, because the
    detector must run against events replayed from storage where no plant
    object exists. ``tests/test_detector.py`` asserts the two stay in
    agreement.

    A field is only reported as missing when a check actually wanted it.
    An unknown inlet valve while the pump is off blocks nothing and is not
    reported, which keeps ``INSUFFICIENT_CONTEXT`` meaningful.

    A non-physical tank level raises ``LEVEL_OUT_OF_RANGE`` **and** still
    feeds the high-limit check. Suppressing the limit check would let a
    forged out-of-range reading downgrade a critical finding to a medium
    one, so over-reporting is chosen deliberately here.

    Args:
        event: The event under evaluation.

    Returns:
        Zero or more alerts, in no particular order.

    """
    process = event.process
    base = _event_evidence(event)
    alerts: list[Alert] = []
    missing: list[str] = []

    pump_state = process.pump_state
    if pump_state not in PUMP_STATES:
        missing.append("pump_state")
    pump_on = pump_state == "on"

    if pump_on:
        inlet_state = _resolve_inlet_state(process)
        if inlet_state not in VALVE_STATES:
            missing.append("inlet_valve_state")
        elif inlet_state == "closed":
            alerts.append(
                build_alert(
                    event.event_id,
                    ReasonCode.UNSAFE_PUMP_START,
                    {
                        **base,
                        "pump_state": pump_state,
                        "inlet_valve_state": inlet_state,
                        "tank_level": process.tank_level,
                    },
                )
            )

        if process.power_source not in POWER_SOURCES:
            missing.append("power_source")
        elif process.power_source == "off":
            alerts.append(
                build_alert(
                    event.event_id,
                    ReasonCode.PUMP_WITHOUT_POWER,
                    {
                        **base,
                        "pump_state": pump_state,
                        "power_source": process.power_source,
                        "tank_level": process.tank_level,
                    },
                )
            )

    high_limit = process.high_level_limit
    target_level = process.target_level
    if high_limit is None:
        missing.append("high_level_limit")
    if target_level is None:
        missing.append("target_level")

    if high_limit is not None:
        if event.mode == "running" and process.tank_level > high_limit:
            alerts.append(
                build_alert(
                    event.event_id,
                    ReasonCode.TANK_ABOVE_HIGH_LIMIT,
                    {
                        **base,
                        "tank_level": process.tank_level,
                        "high_level_limit": high_limit,
                    },
                )
            )
        if target_level is not None and target_level >= high_limit:
            alerts.append(
                build_alert(
                    event.event_id,
                    ReasonCode.SETPOINT_AT_OR_ABOVE_LIMIT,
                    {
                        **base,
                        "target_level": target_level,
                        "high_level_limit": high_limit,
                    },
                )
            )

    lowest, highest = PHYSICAL_LEVEL_RANGE
    if not lowest <= process.tank_level <= highest:
        alerts.append(
            build_alert(
                event.event_id,
                ReasonCode.LEVEL_OUT_OF_RANGE,
                {**base, "tank_level": process.tank_level},
            )
        )

    if missing:
        alerts.append(_insufficient_context(event, missing))
    return alerts


def check_transitions(event: Event, history: Sequence[Event] = ()) -> list[Alert]:
    """Evaluate Layer 2 state-transition rules against one event.

    Layer 1 asks whether the current state is safe. Layer 2 asks whether
    the plant could legitimately have arrived here, which is where a
    protocol-valid command issued at the wrong point in the sequence
    becomes visible.

    Args:
        event: The event under evaluation.
        history: Earlier events from the **same logical run**, oldest
            first, not including ``event``. Only the most recent entry is
            read. Concatenating separate scenarios into one history would
            manufacture a transition across the seam, so the evaluation
            harness must keep runs separate.

    Returns:
        Zero or more alerts, in no particular order.

    """
    process = event.process
    base = _event_evidence(event)
    alerts: list[Alert] = []
    missing: list[str] = []
    mode = event.mode

    if mode == "recovery":
        if process.pump_state not in PUMP_STATES:
            missing.append("pump_state")
        elif process.pump_state == "on":
            alerts.append(
                build_alert(
                    event.event_id,
                    ReasonCode.PUMP_ACTIVE_DURING_RECOVERY,
                    {**base, "pump_state": process.pump_state},
                )
            )

    previous_mode = history[-1].mode if history else None
    if previous_mode is not None and previous_mode != mode:
        transition_evidence = {
            **base,
            "previous_mode": previous_mode,
            "previous_event_id": history[-1].event_id,
        }
        if (previous_mode, mode) not in LEGAL_TRANSITIONS:
            alerts.append(
                build_alert(
                    event.event_id,
                    ReasonCode.ILLEGAL_MODE_TRANSITION,
                    transition_evidence,
                )
            )
        if previous_mode == "recovery":
            if process.power_source not in POWER_SOURCES:
                missing.append("power_source")
            elif process.power_source == "off":
                alerts.append(
                    build_alert(
                        event.event_id,
                        ReasonCode.RECOVERY_OUT_OF_SEQUENCE,
                        {
                            **transition_evidence,
                            "power_source": process.power_source,
                        },
                    )
                )

    if missing:
        alerts.append(_insufficient_context(event, missing))
    return alerts


def _parse_timestamp(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp, returning ``None`` when unavailable."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _command_fingerprint(event: Event) -> tuple[Any, ...]:
    """Return the infrastructure-neutral identity of a command event."""
    return (
        event.command,
        event.target,
        event.value,
        event.raw.get("address"),
        event.raw.get("kind"),
    )


def _process_fingerprint(event: Event) -> tuple[Any, ...]:
    """Return the process context that makes a repeated command meaningful."""
    process = event.process
    return (
        event.mode,
        process.pump_state,
        _resolve_inlet_state(process),
        process.outlet_valve_state,
        process.power_source,
        process.target_level,
        process.high_level_limit,
    )


def _is_risky_replay_context(event: Event) -> bool:
    """Return whether a repeated command is risky in the current context."""
    process = event.process
    if event.target == "pump" and event.value == 1:
        return (
            _resolve_inlet_state(process) == "closed" or process.power_source == "off"
        )
    if event.target == "mode":
        return process.power_source == "off" or event.mode == "recovery"
    return False


def check_replay(event: Event, history: Sequence[Event] = ()) -> list[Alert]:
    """Evaluate Layer 3 replay and event-ordering checks.

    Args:
        event: The event under evaluation.
        history: Earlier events from the same logical run, oldest first.

    Returns:
        Alerts for duplicate sequence IDs, stale timestamps, or replayed
        commands whose process context has changed.

    """
    alerts: list[Alert] = []
    base = _event_evidence(event)

    for previous in history:
        if previous.sequence_id == event.sequence_id:
            alerts.append(
                build_alert(
                    event.event_id,
                    ReasonCode.DUPLICATE_SEQUENCE_ID,
                    {**base, "previous_event_id": previous.event_id},
                )
            )
            break

    if history:
        previous_timestamp = _parse_timestamp(history[-1].timestamp)
        current_timestamp = _parse_timestamp(event.timestamp)
        if (
            previous_timestamp is not None
            and current_timestamp is not None
            and current_timestamp < previous_timestamp
        ):
            alerts.append(
                build_alert(
                    event.event_id,
                    ReasonCode.STALE_TIMESTAMP,
                    {
                        **base,
                        "previous_timestamp": history[-1].timestamp,
                        "previous_event_id": history[-1].event_id,
                    },
                )
            )

    if event.command not in WRITE_COMMANDS:
        return alerts
    if not _is_risky_replay_context(event):
        return alerts

    fingerprint = _command_fingerprint(event)
    current_context = _process_fingerprint(event)
    for index, previous in enumerate(reversed(history), start=1):
        if previous.command not in WRITE_COMMANDS:
            continue
        if _command_fingerprint(previous) != fingerprint:
            continue
        if index < REPLAY_CONTEXT_WINDOW:
            continue
        if _process_fingerprint(previous) == current_context:
            continue
        alerts.append(
            build_alert(
                event.event_id,
                ReasonCode.COMMAND_REPLAY,
                {
                    **base,
                    "previous_event_id": previous.event_id,
                    "events_since_previous": index,
                },
            )
        )
        break
    return alerts


def _setpoint_value(event: Event) -> float | None:
    """Return a numeric setpoint command value, if this event carries one."""
    if event.command not in WRITE_COMMANDS or event.target not in SETPOINT_TARGETS:
        return None
    if isinstance(event.value, int | float):
        return float(event.value)
    return None


def check_rate_and_drift(event: Event, history: Sequence[Event] = ()) -> list[Alert]:
    """Evaluate Layer 4 command-rate and cumulative drift checks.

    Args:
        event: The event under evaluation.
        history: Earlier events from the same logical run, oldest first.

    Returns:
        Alerts when a target is written too frequently or a setpoint moves
        cumulatively outside the benign maintenance cadence.

    """
    if event.command not in WRITE_COMMANDS:
        return []

    alerts: list[Alert] = []
    base = _event_evidence(event)
    window = [*history[-(RATE_WINDOW_EVENTS - 1) :], event]
    matching_writes = [
        candidate
        for candidate in window
        if candidate.command in WRITE_COMMANDS and candidate.target == event.target
        if candidate.value == event.value
    ]
    if (
        event.target not in SETPOINT_TARGETS
        and len(matching_writes) > RATE_MAX_WRITES_PER_TARGET
    ):
        alerts.append(
            build_alert(
                event.event_id,
                ReasonCode.COMMAND_RATE_SPIKE,
                {
                    **base,
                    "command_count": len(matching_writes),
                    "window_events": RATE_WINDOW_EVENTS,
                },
            )
        )

    current_value = _setpoint_value(event)
    if current_value is None or event.mode == "maintenance":
        return alerts

    drift_window = [*history[-(SETPOINT_DRIFT_WINDOW_EVENTS - 1) :], event]
    values = [
        value
        for candidate in drift_window
        if candidate.mode == event.mode
        if candidate.target == event.target
        for value in [_setpoint_value(candidate)]
        if value is not None
    ]
    if len(values) >= 3:
        delta = values[-1] - values[0]
        monotonic_up = all(
            after >= before for before, after in zip(values, values[1:], strict=False)
        )
        if monotonic_up and delta > SETPOINT_DRIFT_LIMIT_PERCENT:
            alerts.append(
                build_alert(
                    event.event_id,
                    ReasonCode.SETPOINT_DRIFT,
                    {
                        **base,
                        "delta": delta,
                        "window_events": SETPOINT_DRIFT_WINDOW_EVENTS,
                    },
                )
            )
    return alerts


def _merge_context_alerts(event: Event, alerts: Sequence[Alert]) -> list[Alert]:
    """Collapse per-layer context alerts into one alert for the event.

    Alert identity is ``(event_id, reason_code)``, so two layers each
    reporting missing context would emit two alerts sharing one
    ``alert_id``. The merged alert lists the union of blocked fields and
    its explanation is re-rendered from that union.

    Args:
        event: The event under evaluation.
        alerts: Alerts collected from all layers.

    Returns:
        A list with at most one ``INSUFFICIENT_CONTEXT`` alert.

    """
    context = [a for a in alerts if a.reason_code == ReasonCode.INSUFFICIENT_CONTEXT]
    if len(context) <= 1:
        return list(alerts)
    fields = sorted({f for a in context for f in a.evidence["missing_fields"]})
    others = [a for a in alerts if a.reason_code != ReasonCode.INSUFFICIENT_CONTEXT]
    return [*others, _insufficient_context(event, fields)]


def _severity_sort_key(alert: Alert) -> tuple[int, str]:
    """Return a sort key ordering alerts most urgent first, then by code."""
    return (-SEVERITY_RANK[Severity(alert.severity)], str(alert.reason_code))


def detect(
    event: Event,
    history: Sequence[Event] = (),
    *,
    baseline_profile=None,
) -> list[Alert]:
    """Run every implemented layer over one event.

    This is the detector's public entry point, as published in
    ``team_handoff.md``. It is pure: the same event and history always
    produce the same alerts, with the same identifiers.

    Args:
        event: The event under evaluation.
        history: Earlier events from the same logical run, oldest first,
            not including ``event``.
        baseline_profile: Optional Layer 5 profile trained from benign
            scenarios. When omitted, only deterministic layers run.

    Returns:
        Alerts ordered most urgent first, with at most one alert per
        ``(event, reason_code)`` pair. An empty list means every
        implemented check ran and none fired — not that the event is
        proven safe.

    """
    alerts = [
        *check_invariants(event),
        *check_transitions(event, history),
        *check_replay(event, history),
        *check_rate_and_drift(event, history),
    ]
    if baseline_profile is not None:
        from .baseline import check_baseline

        alerts.extend(check_baseline(event, history, baseline_profile))
    return sorted(_merge_context_alerts(event, alerts), key=_severity_sort_key)
