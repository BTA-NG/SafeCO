"""Scenario-level detector evaluation for SafeCO.

The evaluator replays complete deterministic scenarios through the same
``Event`` and ``Alert`` contracts used by the live pipeline. It keeps one
history per scenario so transition, replay, and drift checks never see
events from another run.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .alerts import SEVERITY_RANK, Alert, ReasonCode, Severity
from .baseline import BaselineProfile, train_baseline
from .collector import EventCollector
from .detector import detect
from .events import Event, ProcessSnapshot
from .plant import PlantState
from .scenarios import (
    ATTACK_JITTER_SCENARIOS,
    ATTACK_SCENARIOS,
    GROUND_TRUTH,
    NORMAL_SCENARIOS,
    AnomalyPlan,
    run_scenario,
)
from .simulator import CommandRecord
from .storage import EventStore

EXPECTED_ATTACK_ALERTS: dict[str, ReasonCode] = {
    "attack_baseline_high_limit_01": ReasonCode.BASELINE_DEVIATION,
    "attack_baseline_low_tank_01": ReasonCode.BASELINE_DEVIATION,
    "attack_baseline_mode_context_01": ReasonCode.BASELINE_DEVIATION,
    "attack_injection_01": ReasonCode.UNSAFE_PUMP_START,
    "attack_replay_01": ReasonCode.COMMAND_REPLAY,
    "attack_mistimed_01": ReasonCode.RECOVERY_OUT_OF_SEQUENCE,
    "attack_drift_01": ReasonCode.SETPOINT_DRIFT,
    "attack_injection_jitter_01": ReasonCode.UNSAFE_PUMP_START,
    "attack_replay_jitter_01": ReasonCode.COMMAND_REPLAY,
    "attack_mistimed_jitter_01": ReasonCode.RECOVERY_OUT_OF_SEQUENCE,
    "attack_drift_jitter_01": ReasonCode.SETPOINT_DRIFT,
}
"""Expected primary detector reason for each required attack scenario."""

BENIGN_EVALUATION_SCENARIOS: tuple[str, ...] = tuple(sorted(NORMAL_SCENARIOS))
ATTACK_EVALUATION_SCENARIOS: tuple[str, ...] = tuple(
    sorted({*ATTACK_SCENARIOS, *ATTACK_JITTER_SCENARIOS})
)
DEFAULT_EVALUATION_SCENARIOS: tuple[str, ...] = (
    *BENIGN_EVALUATION_SCENARIOS,
    *ATTACK_EVALUATION_SCENARIOS,
)

TUNING_SCENARIOS: tuple[str, ...] = (
    "startup_01",
    "steady_running_01",
    "maintenance_01",
    "attack_baseline_low_tank_01",
    "attack_injection_01",
    "attack_drift_01",
)
VALIDATION_SCENARIOS: tuple[str, ...] = (
    "controlled_shutdown_01",
    "grid_recovery_01",
    "attack_replay_01",
)
HELD_OUT_SCENARIOS: tuple[str, ...] = (
    "extended_normal_01",
    "attack_mistimed_01",
    "attack_baseline_mode_context_01",
)

BASELINE_TRAINING_SCENARIOS: tuple[str, ...] = tuple(
    scenario_id for scenario_id in TUNING_SCENARIOS if scenario_id in NORMAL_SCENARIOS
)
"""Benign tuning scenarios used for Layer 5 training without held-out leakage."""


@dataclass(frozen=True)
class ScenarioTrace:
    """Persisted command-event trace for one deterministic scenario."""

    scenario_id: str
    ground_truth: str
    seed: int
    duration_s: float
    events: tuple[Event, ...]
    event_elapsed_s: tuple[float, ...]


@dataclass(frozen=True)
class ClassificationSummary:
    """Scenario-level confusion-matrix counts."""

    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int


@dataclass(frozen=True)
class ScenarioEvaluation:
    """Detector result summary for one complete scenario."""

    detector_mode: str
    scenario_id: str
    ground_truth: str
    duration_s: float
    event_count: int
    alert_count: int
    actionable_alert_count: int
    reason_codes: tuple[ReasonCode, ...]
    expected_reason_code: ReasonCode | None
    detected_expected: bool
    predicted_attack: bool
    classification: str
    first_detection_sequence_id: int | None
    first_detection_event_id: str | None
    detection_latency_events: int | None
    detection_latency_s: float | None


@dataclass(frozen=True)
class EvaluationReport:
    """Aggregate detector metrics across complete scenarios."""

    detector_mode: str
    scenarios: tuple[ScenarioEvaluation, ...]
    precision: float
    recall: float
    false_alerts_per_normal_hour: float
    missed_attacks: tuple[str, ...]
    maintenance_false_positives: int
    classification: ClassificationSummary


@dataclass(frozen=True)
class EvaluationComparison:
    """Rule-only and baseline-enabled reports over the same scenarios."""

    rules_only: EvaluationReport
    with_baseline: EvaluationReport


def _is_actionable(alert: Alert) -> bool:
    """Return whether an alert should count as an operator-facing finding."""
    return SEVERITY_RANK[Severity(alert.severity)] > SEVERITY_RANK[Severity.LOW]


_TRACE_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
"""Synthetic epoch for deterministic evaluation timestamps.

Evaluation traces must be seed-reproducible; wall-clock timestamps are not
and can invert under clock adjustment (a phantom ``STALE_TIMESTAMP``
false positive on benign scenarios).
"""


def _process_at(state: PlantState, observed: dict[str, Any]) -> ProcessSnapshot:
    """Merge command-time plant state with the step's observed telemetry.

    Discrete fields (mode, power source, valves, pump) come from the plant
    at the moment the command was issued, so multi-command steps keep their
    intermediate modes visible to the detector's transition checks. Analog
    fields (``tank_level``, ``target_level``, ``high_level_limit``) come
    from the step's observed snapshot, so benign anomalies (noise, spike,
    nudge, jitter) are exercised in the evaluated feature vector.
    """
    return ProcessSnapshot(
        tank_level=observed["tank_level"],
        valve_state="open" if state.inlet_valve_open else "closed",
        pump_state="on" if state.pump_on else "off",
        inlet_valve_state="open" if state.inlet_valve_open else "closed",
        outlet_valve_state="open" if state.outlet_valve_open else "closed",
        mode=state.mode.name.lower(),
        power_source=state.power_source.name.lower(),
        target_level=observed["target_level"],
        high_level_limit=observed["high_level_limit"],
    )


def events_for_scenario(
    scenario_id: str,
    seed: int = 42,
    *,
    database: str | Path | None = None,
    anomaly_plan: AnomalyPlan | None = None,
) -> ScenarioTrace:
    """Run a scenario and return its persisted command-event trace.

    Args:
        scenario_id: Registered normal or attack scenario ID.
        seed: Deterministic simulator seed.
        database: Optional SQLite database path. When omitted, a temporary
            database is used for the duration of trace creation.
        anomaly_plan: Optional benign-perturbation schedule. ``None`` uses
            the scenario's registered plan; an empty list reproduces the
            clean base scenario.

    Returns:
        A deterministic command-event trace with ground truth labels. Each
        event's ``process`` merges the command-time plant state (mode, power
        source, valves, pump) with the step's observed telemetry
        (``tank_level``, ``target_level``, ``high_level_limit``) so benign
        anomalies are exercised without manufacturing mode transitions
        inside multi-command steps.

    """
    if database is None:
        with tempfile.TemporaryDirectory() as temp_dir:
            return events_for_scenario(
                scenario_id,
                seed,
                database=Path(temp_dir) / "events.db",
                anomaly_plan=anomaly_plan,
            )

    store = EventStore(database)
    collector = EventCollector(store, scenario_id, seed=seed)
    ground_truth = GROUND_TRUTH.get(scenario_id, "normal")
    events: list[Event] = []
    event_elapsed_s: list[float] = []
    step_of_event: list[int] = []
    pending: list[tuple[CommandRecord, PlantState]] = []
    step_index = 0
    is_attack = (
        scenario_id in ATTACK_SCENARIOS or scenario_id in ATTACK_JITTER_SCENARIOS
    )

    def on_command(command: CommandRecord, state: PlantState) -> None:
        pending.append((command, replace(state)))

    def on_snapshot(snapshot: dict[str, Any]) -> None:
        nonlocal step_index
        for command, state in pending:
            event = collector.record_simulator_command(
                None,
                command,
                source="attacker" if is_attack else "scheduler",
                ground_truth=ground_truth,
                process=_process_at(state, snapshot),
            )
            events.append(event)
            step_of_event.append(step_index)
        pending.clear()
        step_index += 1

    result = run_scenario(
        scenario_id,
        seed,
        anomaly_plan=anomaly_plan,
        on_command=on_command,
        on_snapshot=on_snapshot,
    )
    step_starts: list[float] = []
    elapsed_s = 0.0
    for duration in result.step_durations:
        step_starts.append(elapsed_s)
        elapsed_s += duration
    for index, event in enumerate(events):
        step_elapsed_s = step_starts[step_of_event[index]]
        stamped = _TRACE_EPOCH + timedelta(seconds=step_elapsed_s)
        events[index] = replace(event, timestamp=stamped.isoformat())
        event_elapsed_s.append(step_elapsed_s)
    store.close()
    return ScenarioTrace(
        scenario_id=scenario_id,
        ground_truth=ground_truth,
        seed=seed,
        duration_s=elapsed_s,
        events=tuple(events),
        event_elapsed_s=tuple(event_elapsed_s),
    )


def evaluate_scenario(
    scenario_id: str,
    seed: int = 42,
    *,
    database: str | Path | None = None,
    baseline_profile: BaselineProfile | None = None,
) -> ScenarioEvaluation:
    """Evaluate one complete scenario against the detector."""
    trace = events_for_scenario(scenario_id, seed, database=database)
    history: list[Event] = []
    alerts: list[Alert] = []
    first_detection_sequence_id: int | None = None
    first_detection_event_id: str | None = None
    first_detection_elapsed_s: float | None = None
    detector_mode = "with_baseline" if baseline_profile is not None else "rules_only"

    for event, elapsed_s in zip(trace.events, trace.event_elapsed_s, strict=True):
        event_alerts = detect(event, history, baseline_profile=baseline_profile)
        if first_detection_sequence_id is None and any(
            _is_actionable(alert) for alert in event_alerts
        ):
            first_detection_sequence_id = event.sequence_id
            first_detection_event_id = event.event_id
            first_detection_elapsed_s = elapsed_s
        alerts.extend(event_alerts)
        history.append(event)

    expected_reason = EXPECTED_ATTACK_ALERTS.get(scenario_id)
    reason_codes = tuple(alert.reason_code for alert in alerts)
    is_attack = expected_reason is not None
    detected_expected = expected_reason in reason_codes if is_attack else False
    predicted_attack = (
        detected_expected
        if is_attack
        else any(_is_actionable(alert) for alert in alerts)
    )
    if is_attack:
        classification = "TP" if detected_expected else "FN"
    else:
        classification = "FP" if predicted_attack else "TN"
    attack_start_sequence_id = (
        trace.events[0].sequence_id if is_attack and trace.events else None
    )
    attack_start_elapsed_s = (
        trace.event_elapsed_s[0] if is_attack and trace.events else None
    )
    return ScenarioEvaluation(
        detector_mode=detector_mode,
        scenario_id=scenario_id,
        ground_truth=trace.ground_truth,
        duration_s=trace.duration_s,
        event_count=len(trace.events),
        alert_count=len(alerts),
        actionable_alert_count=sum(1 for alert in alerts if _is_actionable(alert)),
        reason_codes=reason_codes,
        expected_reason_code=expected_reason,
        detected_expected=detected_expected,
        predicted_attack=predicted_attack,
        classification=classification,
        first_detection_sequence_id=first_detection_sequence_id,
        first_detection_event_id=first_detection_event_id,
        detection_latency_events=(
            first_detection_sequence_id - attack_start_sequence_id
            if first_detection_sequence_id is not None
            and attack_start_sequence_id is not None
            else None
        ),
        detection_latency_s=(
            first_detection_elapsed_s - attack_start_elapsed_s
            if first_detection_elapsed_s is not None
            and attack_start_elapsed_s is not None
            else None
        ),
    )


def evaluate_scenarios(
    scenario_ids: Sequence[str] = DEFAULT_EVALUATION_SCENARIOS,
    seed: int = 42,
    *,
    baseline_profile: BaselineProfile | None = None,
) -> EvaluationReport:
    """Evaluate multiple complete scenarios and compute summary metrics."""
    evaluations = tuple(
        evaluate_scenario(scenario_id, seed, baseline_profile=baseline_profile)
        for scenario_id in scenario_ids
    )
    attack_results = [
        result for result in evaluations if result.expected_reason_code is not None
    ]
    true_positives = sum(1 for result in attack_results if result.detected_expected)
    false_positive_scenarios = [
        result
        for result in evaluations
        if result.expected_reason_code is None and result.actionable_alert_count > 0
    ]
    predicted_positive_scenarios = true_positives + len(false_positive_scenarios)
    precision = (
        true_positives / predicted_positive_scenarios
        if predicted_positive_scenarios
        else 0.0
    )
    recall = true_positives / len(attack_results) if attack_results else 0.0
    benign_duration_hours = sum(
        result.duration_s / 3600.0
        for result in evaluations
        if result.expected_reason_code is None
    )
    benign_alerts = sum(
        result.actionable_alert_count
        for result in evaluations
        if result.expected_reason_code is None
    )
    return EvaluationReport(
        detector_mode="with_baseline" if baseline_profile is not None else "rules_only",
        scenarios=evaluations,
        precision=precision,
        recall=recall,
        false_alerts_per_normal_hour=(
            benign_alerts / benign_duration_hours if benign_duration_hours else 0.0
        ),
        missed_attacks=tuple(
            result.scenario_id
            for result in attack_results
            if not result.detected_expected
        ),
        maintenance_false_positives=sum(
            result.actionable_alert_count
            for result in evaluations
            if result.ground_truth == "maintenance"
        ),
        classification=ClassificationSummary(
            true_positive=sum(
                1 for result in evaluations if result.classification == "TP"
            ),
            false_positive=sum(
                1 for result in evaluations if result.classification == "FP"
            ),
            true_negative=sum(
                1 for result in evaluations if result.classification == "TN"
            ),
            false_negative=sum(
                1 for result in evaluations if result.classification == "FN"
            ),
        ),
    )


def train_baseline_from_scenarios(
    scenario_ids: Sequence[str] = BASELINE_TRAINING_SCENARIOS,
    seed: int = 42,
) -> BaselineProfile:
    """Train a Layer 5 baseline from benign scenario IDs.

    Args:
        scenario_ids: Scenario IDs to use as baseline training data.
        seed: Deterministic simulator seed.

    Returns:
        A robust statistical baseline profile.

    Raises:
        ValueError: If any attack scenario is included in training.

    """
    attacks = set(scenario_ids) & set(ATTACK_SCENARIOS)
    if attacks:
        raise ValueError(
            f"baseline training received attack scenarios: {sorted(attacks)}"
        )
    traces = {
        scenario_id: events_for_scenario(scenario_id, seed).events
        for scenario_id in scenario_ids
    }
    return train_baseline(traces, seed=seed)


def train_baseline_for_evaluation(seed: int = 42) -> BaselineProfile:
    """Train the default evaluation baseline without validation or held-out data."""
    return train_baseline_from_scenarios(BASELINE_TRAINING_SCENARIOS, seed)


def compare_rule_and_baseline(
    scenario_ids: Sequence[str] = DEFAULT_EVALUATION_SCENARIOS,
    seed: int = 42,
) -> EvaluationComparison:
    """Evaluate the same scenarios in rule-only and baseline-enabled modes."""
    baseline_profile = train_baseline_for_evaluation(seed=seed)
    return EvaluationComparison(
        rules_only=evaluate_scenarios(scenario_ids, seed),
        with_baseline=evaluate_scenarios(
            scenario_ids,
            seed,
            baseline_profile=baseline_profile,
        ),
    )


def sample_evidence_pairs(
    scenario_ids: Sequence[str] = ATTACK_EVALUATION_SCENARIOS,
    seed: int = 42,
    *,
    baseline_profile: BaselineProfile | None = None,
) -> dict[str, dict[str, Any]]:
    """Return one representative event/alert JSON pair per scenario."""
    samples: dict[str, dict[str, Any]] = {}
    for scenario_id in scenario_ids:
        trace = events_for_scenario(scenario_id, seed)
        expected = EXPECTED_ATTACK_ALERTS.get(scenario_id)
        history: list[Event] = []
        for event in trace.events:
            alerts = detect(event, history, baseline_profile=baseline_profile)
            selected = next(
                (alert for alert in alerts if alert.reason_code == expected),
                next((alert for alert in alerts if _is_actionable(alert)), None),
            )
            if selected is not None:
                samples[scenario_id] = {
                    "event": event.to_dict(),
                    "alert": selected.to_dict(),
                }
                break
            history.append(event)
    return samples


def _json_default(value: Any) -> Any:
    """Return JSON-safe values for dataclasses and enums."""
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


def _report_to_dict(report: EvaluationReport) -> dict[str, Any]:
    """Return a JSON-friendly evaluation report."""
    return json.loads(json.dumps(report, default=_json_default))


def _print_report(report: EvaluationReport) -> None:
    """Print a compact human-readable evaluation report."""
    print("SafeCO Detector Evaluation")
    print(f"Mode: {report.detector_mode}")
    print(f"Scenarios: {len(report.scenarios)}")
    print(f"Precision: {report.precision:.3f}")
    print(f"Recall: {report.recall:.3f}")
    print(f"False alerts / normal hour: {report.false_alerts_per_normal_hour:.3f}")
    print(
        "Classification: "
        f"TP={report.classification.true_positive} "
        f"FP={report.classification.false_positive} "
        f"TN={report.classification.true_negative} "
        f"FN={report.classification.false_negative}"
    )
    print()
    print("Scenario table:")
    headers = (
        "scenario_id",
        "truth",
        "class",
        "alerts",
        "latency_s",
        "expected_reason",
    )
    rows = []
    for scenario in report.scenarios:
        latency = (
            f"{scenario.detection_latency_s:.2f}"
            if scenario.detection_latency_s is not None
            else "-"
        )
        rows.append(
            (
                scenario.scenario_id,
                scenario.ground_truth,
                scenario.classification,
                str(scenario.actionable_alert_count),
                latency,
                str(scenario.expected_reason_code or "-"),
            )
        )
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]
    numeric_columns = {3, 4}

    def render_row(row: Sequence[str]) -> str:
        cells = []
        for index, value in enumerate(row):
            align = str.rjust if index in numeric_columns else str.ljust
            cells.append(align(value, widths[index]))
        return " | ".join(cells)

    print(render_row(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(render_row(row))


def main(argv: Sequence[str] | None = None) -> int:
    """Run detector evaluation from the command line."""
    parser = argparse.ArgumentParser(description="Run SafeCO detector evaluation")
    parser.add_argument("--without-baseline", action="store_true")
    parser.add_argument("--held-out", action="store_true")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--samples-json", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    scenario_ids = HELD_OUT_SCENARIOS if args.held_out else DEFAULT_EVALUATION_SCENARIOS
    baseline_profile = (
        None if args.without_baseline else train_baseline_for_evaluation(args.seed)
    )

    if args.samples_json:
        samples = sample_evidence_pairs(
            ATTACK_EVALUATION_SCENARIOS,
            args.seed,
            baseline_profile=baseline_profile,
        )
        print(json.dumps(samples, indent=2, default=_json_default))
        return 0

    if args.compare:
        comparison = compare_rule_and_baseline(scenario_ids, args.seed)
        if args.as_json:
            print(json.dumps(comparison, indent=2, default=_json_default))
        else:
            _print_report(comparison.rules_only)
            print()
            _print_report(comparison.with_baseline)
        return 0

    report = evaluate_scenarios(
        scenario_ids,
        args.seed,
        baseline_profile=baseline_profile,
    )
    if args.as_json:
        print(json.dumps(_report_to_dict(report), indent=2))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
