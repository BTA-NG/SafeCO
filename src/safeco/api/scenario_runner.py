"""Run a registered scenario and persist its events and alerts.

This is orchestration wiring for the dashboard, not new plant or detector logic.
It drives the existing ``PlantSimulator`` through a registered scenario's steps,
persists each command as an ``Event`` via ``EventCollector``, runs the pure
``detect`` function over the growing history, and stores any findings in the
``AlertStore``. The result mirrors ``scenarios._execute`` so the seed
fingerprint stays identical to a direct ``run_scenario`` call.

SafeCO stays advisory: this triggers the simulator so consequences can be
observed and explained. It never blocks a command and never acts on the plant.
"""

from __future__ import annotations

from safeco.alert_store import AlertStore
from safeco.collector import EventCollector
from safeco.detector import detect
from safeco.events import Event
from safeco.scenarios import (
    ATTACK_SCENARIOS,
    GROUND_TRUTH,
    NORMAL_SCENARIOS,
    ScenarioResult,
    scenario_fingerprint,
)
from safeco.simulator import CommandRecord, PlantSimulator
from safeco.storage import EventStore


def run_scenario_and_persist(
    name: str,
    seed: int,
    event_store: EventStore,
    alert_store: AlertStore,
) -> dict[str, object]:
    """Run one scenario, persisting its events and detector alerts.

    Args:
        name: Scenario registry key (normal or attack).
        seed: Deterministic seed forwarded to the simulator.
        event_store: Store that receives the scenario's events.
        alert_store: Store that receives the detector's findings.

    Returns:
        A JSON-friendly summary: scenario id, seed, ground truth, number of
        persisted events, number of distinct alerts, any invariant violations,
        and the reproducibility fingerprint.

    Raises:
        KeyError: If ``name`` is not a known scenario.

    """
    registry = {**NORMAL_SCENARIOS, **ATTACK_SCENARIOS}
    if name not in registry:
        raise KeyError(f"unknown scenario {name!r}")

    ground_truth = GROUND_TRUTH.get(name, "normal")
    steps = registry[name]()
    simulator = PlantSimulator(seed=seed)
    collector = EventCollector(event_store, name, seed=seed)
    result = ScenarioResult(name, seed, ground_truth=ground_truth)
    history: list[Event] = []
    alert_ids: set[str] = set()

    def on_command(command: CommandRecord) -> None:
        # Fired the moment a command is applied, before physics advances — the
        # same context the collector persists in runtime integration.
        event = collector.record_simulator_command(
            simulator, command, ground_truth=ground_truth
        )
        for alert in detect(event, history):
            alert_store.upsert(alert)
            alert_ids.add(alert.alert_id)
        history.append(event)

    simulator.on_command = on_command
    for phase, seconds, action in steps:
        if action is not None:
            action(simulator)
        result.violations.append(simulator.step(seconds))
        snapshot = simulator.snapshot()
        snapshot["phase"] = phase
        result.snapshots.append(snapshot)
    result.commands.extend(simulator.commands)

    return {
        "scenario_id": name,
        "seed": seed,
        "ground_truth": ground_truth,
        "events": len(history),
        "alerts": len(alert_ids),
        "violations": [step for step in result.violations if step],
        "fingerprint": scenario_fingerprint(result),
    }
