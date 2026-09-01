"""Structured alert contract shared by the detector, API, and dashboard.

This schema is a frozen interface. The detector emits ``Alert`` objects,
the FastAPI layer serves them, and the dashboard renders them. Field
names, the ``ReasonCode`` vocabulary, and ``CONTRACT_FIELDS`` ordering
must not change without a compatibility note in the pull request.

Engineer-facing wording lives in ``TEMPLATES`` rather than inside
detection logic. The person reading an alert is an engineer under
pressure, not a security specialist, so the copy they see is reviewable
in one place instead of scattered across rule branches.

Alert identity is derived, not random: see ``derive_alert_id``.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from typing import Any

ALERT_NAMESPACE = uuid.UUID("6f3c0a1e-5b7d-4f2a-9c84-1d0e7a2b4c53")
"""Fixed namespace for UUID5 alert identifiers. Never change this value.

Changing it renames every historical alert and orphans acknowledgement
state recorded against the old identifiers.
"""

CONTRACT_FIELDS: tuple[str, ...] = (
    "alert_id",
    "event_id",
    "severity",
    "reason_code",
    "title",
    "explanation",
    "evidence",
    "recommended_action",
    "confidence",
    "acknowledged",
)
"""Frozen field order of the alert contract, as published in team_handoff.md."""


class AlertContractError(ValueError):
    """An alert could not be built from the frozen contract."""


class Severity(StrEnum):
    """Graded alert severity. Compare with ``SEVERITY_RANK``, not ``<``."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_RANK: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}
"""Sortable urgency rank. ``Severity`` is a string enum and does not order."""


class ReasonCode(StrEnum):
    """Stable machine-readable vocabulary of detector findings."""

    # Layer 1 - safety invariants
    UNSAFE_PUMP_START = "unsafe_pump_start"
    PUMP_WITHOUT_POWER = "pump_without_power"
    TANK_ABOVE_HIGH_LIMIT = "tank_above_high_limit"
    SETPOINT_AT_OR_ABOVE_LIMIT = "setpoint_at_or_above_limit"
    LEVEL_OUT_OF_RANGE = "level_out_of_range"

    # Layer 2 - state-transition validation
    ILLEGAL_MODE_TRANSITION = "illegal_mode_transition"
    RECOVERY_OUT_OF_SEQUENCE = "recovery_out_of_sequence"
    PUMP_ACTIVE_DURING_RECOVERY = "pump_active_during_recovery"

    # Layer 3 - replay and sequence validation
    DUPLICATE_SEQUENCE_ID = "duplicate_sequence_id"
    STALE_TIMESTAMP = "stale_timestamp"
    COMMAND_REPLAY = "command_replay"

    # Layer 4 - command rate and drift validation
    COMMAND_RATE_SPIKE = "command_rate_spike"
    SETPOINT_DRIFT = "setpoint_drift"

    # Layer 5 - statistical baseline
    BASELINE_DEVIATION = "baseline_deviation"

    # Cross-layer
    INSUFFICIENT_CONTEXT = "insufficient_context"


@dataclass(frozen=True)
class AlertTemplate:
    """Engineer-facing copy and defaults for one reason code.

    Attributes:
        title: Short headline naming the equipment and the problem.
        explanation: ``str.format`` template rendered against the alert's
            evidence. Float placeholders carry their own format spec so
            evidence keeps full precision while the sentence stays legible.
        recommended_action: The human step SafeCO advises. Never phrased
            as an action SafeCO has taken or will take.
        severity: Default severity for this reason code.
        confidence: Default confidence in the stated finding. Below 1.0
            only where the rule itself is an inference rather than a
            direct observation.

    """

    title: str
    explanation: str
    recommended_action: str
    severity: Severity
    confidence: float = 1.0


TEMPLATES: dict[ReasonCode, AlertTemplate] = {
    ReasonCode.UNSAFE_PUMP_START: AlertTemplate(
        title="Pump running with inlet valve closed",
        explanation=(
            "The pump is running while the inlet valve is closed, so the pump "
            "has no inlet flow path. Tank level {tank_level:.2f}% in "
            "{mode} mode."
        ),
        recommended_action=(
            "SafeCO has not changed the plant. Confirm who issued the pump "
            "command, then inspect the inlet valve before changing pump state."
        ),
        severity=Severity.HIGH,
    ),
    ReasonCode.PUMP_WITHOUT_POWER: AlertTemplate(
        title="Pump commanded on with no power source",
        explanation=(
            "The pump is commanded on while the recorded power source is "
            "'{power_source}'. Tank level {tank_level:.2f}% in {mode} mode."
        ),
        recommended_action=(
            "Verify grid and generator status, and confirm the pump command "
            "before power is restored."
        ),
        severity=Severity.HIGH,
    ),
    ReasonCode.TANK_ABOVE_HIGH_LIMIT: AlertTemplate(
        title="Tank above its high-level limit",
        explanation=(
            "Tank level {tank_level:.2f}% exceeds the configured high-level "
            "limit {high_level_limit:.2f}% while in {mode} mode."
        ),
        recommended_action=(
            "Escalate now. Check the tank for overflow and confirm the outlet "
            "path is open."
        ),
        severity=Severity.CRITICAL,
    ),
    ReasonCode.SETPOINT_AT_OR_ABOVE_LIMIT: AlertTemplate(
        title="Target level is not below the high-level limit",
        explanation=(
            "The target level {target_level:.2f}% is at or above the "
            "high-level limit {high_level_limit:.2f}%, which removes the "
            "safety margin the limit exists to provide."
        ),
        recommended_action=(
            "Confirm who changed the setpoint, then restore a target below "
            "the high-level limit."
        ),
        severity=Severity.HIGH,
    ),
    ReasonCode.LEVEL_OUT_OF_RANGE: AlertTemplate(
        title="Tank level reading outside physical range",
        explanation=(
            "Reported tank level {tank_level:.2f}% is outside the physical "
            "range 0-100%. This points to a sensor or data fault rather than "
            "a process action."
        ),
        recommended_action=(
            "Treat level-based readings as unreliable and check the level "
            "sensor and its data path."
        ),
        severity=Severity.MEDIUM,
    ),
    ReasonCode.ILLEGAL_MODE_TRANSITION: AlertTemplate(
        title="Operating mode changed along an unexpected path",
        explanation=(
            "Operating mode changed from {previous_mode} to {mode}, which is "
            "not an expected transition for this plant."
        ),
        recommended_action=(
            "Confirm with the control room whether this mode change was "
            "intended before acting on it."
        ),
        severity=Severity.HIGH,
        # The legal transition table is derived from observed benign
        # scenarios, so it may be incomplete. That uncertainty belongs in
        # the alert rather than hidden behind a rule that reads as certain.
        confidence=0.8,
    ),
    ReasonCode.RECOVERY_OUT_OF_SEQUENCE: AlertTemplate(
        title="Recovery left before power was restored",
        explanation=(
            "Operating mode moved from recovery to {mode} while the power "
            "source was recorded as '{power_source}'. A power source must be "
            "available before the plant resumes."
        ),
        recommended_action=(
            "Confirm generator or grid availability before allowing startup "
            "to continue."
        ),
        severity=Severity.HIGH,
    ),
    ReasonCode.PUMP_ACTIVE_DURING_RECOVERY: AlertTemplate(
        title="Pump active during power recovery",
        explanation=(
            "The pump is recorded as running while the plant is in recovery "
            "mode. Recovery requires the pump stopped before power transfer."
        ),
        recommended_action=(
            "Confirm the source of the pump command and stop the pump before "
            "power is transferred."
        ),
        severity=Severity.HIGH,
    ),
    ReasonCode.DUPLICATE_SEQUENCE_ID: AlertTemplate(
        title="Repeated event sequence number",
        explanation=(
            "Sequence ID {sequence_id} repeats an earlier event in this run. "
            "The earlier event was {previous_event_id}."
        ),
        recommended_action=(
            "Review the collector feed and compare both events before relying "
            "on their ordering."
        ),
        severity=Severity.MEDIUM,
    ),
    ReasonCode.STALE_TIMESTAMP: AlertTemplate(
        title="Event timestamp moved backwards",
        explanation=(
            "This event timestamp {timestamp} is older than the previous "
            "event timestamp {previous_timestamp} in the same run."
        ),
        recommended_action=(
            "Check the data source clock and verify whether this event arrived "
            "late or was replayed."
        ),
        severity=Severity.MEDIUM,
        confidence=0.9,
    ),
    ReasonCode.COMMAND_REPLAY: AlertTemplate(
        title="Command repeated after plant context changed",
        explanation=(
            "The same {command} command for {target}={value} appeared again "
            "after {events_since_previous} later events and a changed process "
            "context."
        ),
        recommended_action=(
            "Confirm who issued the repeated command and compare it with the "
            "earlier event before making plant changes."
        ),
        severity=Severity.HIGH,
        confidence=0.85,
    ),
    ReasonCode.COMMAND_RATE_SPIKE: AlertTemplate(
        title="Command rate spike on one target",
        explanation=(
            "{target} received {command_count} write commands inside the last "
            "{window_events} events, which is above the expected local cadence."
        ),
        recommended_action=(
            "Pause for operator review and confirm the repeated commands match "
            "the current operating procedure."
        ),
        severity=Severity.MEDIUM,
        confidence=0.8,
    ),
    ReasonCode.SETPOINT_DRIFT: AlertTemplate(
        title="Setpoint drifting toward unsafe operation",
        explanation=(
            "{target} changed by {delta:.2f}% across the last {window_events} "
            "events while the plant was in {mode} mode."
        ),
        recommended_action=(
            "Review recent setpoint changes, confirm authorisation, and restore "
            "the configured safety margin if the change was unintended."
        ),
        severity=Severity.HIGH,
        confidence=0.85,
    ),
    ReasonCode.BASELINE_DEVIATION: AlertTemplate(
        title="Command differs from normal baseline",
        explanation=(
            "This {command} event for {target} in {mode} mode is unusual for "
            "the learned normal baseline. Features outside range: "
            "{features_text}."
        ),
        recommended_action=(
            "Review the event as an anomaly, compare it with recent plant "
            "history, and confirm whether the command matches normal procedure."
        ),
        severity=Severity.MEDIUM,
        confidence=0.75,
    ),
    ReasonCode.INSUFFICIENT_CONTEXT: AlertTemplate(
        title="Not enough process context to complete all checks",
        explanation=(
            "SafeCO could not evaluate every safety check for this event. "
            "Missing or unknown process fields: {missing_fields_text}. The "
            "checks that depend on those fields did not run, so this event "
            "is not confirmed safe."
        ),
        recommended_action=(
            "Restore the missing telemetry fields before relying on SafeCO "
            "for this equipment."
        ),
        severity=Severity.LOW,
    ),
}
"""Engineer-facing copy for every ``ReasonCode``. Kept complete by tests."""


def derive_alert_id(event_id: str, reason_code: ReasonCode) -> str:
    """Return the deterministic identifier for one finding.

    Alert identity is a pure function of the event and the reason code.
    Re-running the detector over stored events therefore regenerates the
    same identifiers instead of creating duplicates, which keeps
    acknowledgement state meaningful across restarts and offline replay,
    and keeps detector output reproducible as required by AGENTS.md.

    Args:
        event_id: Identifier of the event the finding is about.
        reason_code: The finding type.

    Returns:
        A UUID5 string derived from ``ALERT_NAMESPACE``.

    """
    return str(uuid.uuid5(ALERT_NAMESPACE, f"{event_id}:{reason_code}"))


@dataclass(frozen=True)
class Alert:
    """One structured, explainable finding about a single event.

    An alert states that a condition was observed. It never claims
    attribution: deciding that a condition was an attack, and deciding
    what to do about it, are both left to the engineer.

    Attributes:
        event_id: Identifier of the ``Event`` this finding is about.
        reason_code: Stable machine-readable finding type.
        severity: Graded severity.
        title: Short headline for the alert queue.
        explanation: Plain-language description with observed values.
        evidence: Observed values and event context backing the finding.
        recommended_action: The human step SafeCO advises.
        confidence: Confidence in the stated finding, 0.0 to 1.0.
        acknowledged: Whether an engineer has acknowledged the alert.
        alert_id: Deterministic identifier, filled from ``event_id`` and
            ``reason_code`` when not supplied.

    """

    event_id: str
    reason_code: ReasonCode
    severity: Severity
    title: str
    explanation: str
    evidence: dict[str, Any] = field(default_factory=dict)
    recommended_action: str = ""
    confidence: float = 1.0
    acknowledged: bool = False
    alert_id: str = ""

    def __post_init__(self) -> None:
        """Fill the deterministic alert identifier when one was not given."""
        if not self.alert_id:
            object.__setattr__(
                self, "alert_id", derive_alert_id(self.event_id, self.reason_code)
            )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dict in frozen ``CONTRACT_FIELDS`` order."""
        data = asdict(self)
        data["reason_code"] = str(self.reason_code)
        data["severity"] = str(self.severity)
        return {name: data[name] for name in CONTRACT_FIELDS}

    def canonical_json(self) -> str:
        """Return a stable JSON encoding, matching ``Event.canonical_json``."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def acknowledge(self) -> Alert:
        """Return a copy of this alert marked acknowledged.

        ``Alert`` is frozen so acknowledgement produces a new record
        rather than mutating the original finding.
        """
        return replace(self, acknowledged=True)


def build_alert(
    event_id: str,
    reason_code: ReasonCode,
    evidence: dict[str, Any],
    *,
    severity: Severity | None = None,
    confidence: float | None = None,
) -> Alert:
    """Build an alert from its template and evidence.

    Args:
        event_id: Identifier of the event the finding is about.
        reason_code: The finding type; must have a ``TEMPLATES`` entry.
        evidence: Observed values backing the finding. Must supply every
            placeholder the template's explanation references.
        severity: Optional override for the template default.
        confidence: Optional override for the template default.

    Returns:
        A fully rendered ``Alert``.

    Raises:
        AlertContractError: If the reason code has no template, the
            evidence is missing a placeholder the explanation needs, or
            confidence falls outside 0.0 to 1.0.

    """
    template = TEMPLATES.get(reason_code)
    if template is None:
        raise AlertContractError(
            f"no alert template for reason code {reason_code!r}; "
            "add one to TEMPLATES before emitting it"
        )
    resolved_confidence = template.confidence if confidence is None else confidence
    if not 0.0 <= resolved_confidence <= 1.0:
        raise AlertContractError(
            f"confidence {resolved_confidence!r} for {reason_code!r} is "
            "outside the range 0.0 to 1.0"
        )
    try:
        explanation = template.explanation.format(**evidence)
    except KeyError as exc:
        raise AlertContractError(
            f"evidence for {reason_code!r} is missing key {exc.args[0]!r} "
            "required by its explanation template"
        ) from exc
    return Alert(
        event_id=event_id,
        reason_code=reason_code,
        severity=template.severity if severity is None else severity,
        title=template.title,
        explanation=explanation,
        evidence=dict(evidence),
        recommended_action=template.recommended_action,
        confidence=resolved_confidence,
    )
