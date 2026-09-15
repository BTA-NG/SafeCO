"""Run a registered scenario and persist its events and detector alerts.

This is orchestration wiring for the dashboard, not new plant or detector
logic. It drives the canonical ``scenarios.run_scenario`` and, through its
``on_command`` seam, persists each applied command as an ``Event`` via
``EventCollector``, runs the pure ``detect`` function over the growing
history, and stores any findings in the ``AlertStore``.

Composing ``run_scenario`` (rather than re-implementing its step loop) means
the full scenario registry — including the ``ATTACK_JITTER_SCENARIOS`` timing
variants and their duration-jitter plans — is honoured, ``step_durations`` is
populated, and the reproducibility fingerprint stays identical to a direct
``run_scenario`` call. This mirrors ``evaluation.events_for_scenario``, which
uses the same seam.

SafeCO stays advisory: this triggers the simulator so consequences can be
observed and explained. It never blocks a command and never acts on the plant.
"""

from __future__ import annotations

from safeco.alert_store import AlertStore
from safeco.collector import EventCollector
from safeco.detector import detect
from safeco.events import Event
from safeco.plant import PlantState
from safeco.scenarios import GROUND_TRUTH, run_scenario, scenario_fingerprint
from safeco.simulator import CommandRecord
from safeco.storage import EventStore


def run_scenario_and_persist(
    name: str,
    seed: int,
    event_store: EventStore,
    alert_store: AlertStore,
) -> dict[str, object]:
    """Run one scenario, persisting its events and detector alerts.

    Args:
        name: Scenario registry key (normal, attack, or jitter variant).
        seed: Deterministic seed forwarded to the simulator.
        event_store: Store that receives the scenario's events.
        alert_store: Store that receives the detector's findings.

    Returns:
        A JSON-friendly summary: scenario id, seed, ground truth, number of
        persisted events, number of distinct alerts, any invariant violations,
        and the reproducibility fingerprint.

    Raises:
        KeyError: If ``name`` is not a known scenario (raised by ``run_scenario``
            before any event is persisted).

    """
    ground_truth = GROUND_TRUTH.get(name, "normal")
    collector = EventCollector(event_store, name, seed=seed)
    history: list[Event] = []
    alert_ids: set[str] = set()

    def on_command(command: CommandRecord, state: PlantState) -> None:
        # run_scenario fires this the instant a command is applied, before
        # physics advances for the step — the same command-time context the
        # collector records in runtime integration. Persist the command, then
        # run the detector over the prior history (excluding this event).
        event = collector.record(
            state,
            source="scheduler",
            command=f"write_{command.kind}",
            target=command.target,
            value=command.value,
            ground_truth=ground_truth,
            raw={"address": command.address, "kind": command.kind},
        )
        for alert in detect(event, history):
            alert_store.upsert(alert)
            alert_ids.add(alert.alert_id)
        history.append(event)

    result = run_scenario(name, seed, on_command=on_command)

    return {
        "scenario_id": name,
        "seed": seed,
        "ground_truth": result.ground_truth,
        "events": len(history),
        "alerts": len(alert_ids),
        "violations": [step for step in result.violations if step],
        "fingerprint": scenario_fingerprint(result),
    }
