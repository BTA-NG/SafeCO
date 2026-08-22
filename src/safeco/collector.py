from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .events import Event, ProcessSnapshot
from .plant import PlantState
from .storage import EventStore


class EventCollector:
    """Translate plant state/commands into the shared persisted event contract."""

    def __init__(self, store: EventStore, scenario_id: str, seed: int | None = None) -> None:
        self.store = store
        self.scenario_id = scenario_id
        self.seed = seed
        self.sequence_id = 0

    def record(
        self,
        plant: PlantState,
        *,
        source: str,
        command: str,
        target: str,
        value: Any = None,
        ground_truth: str = "normal",
        raw: dict[str, Any] | None = None,
    ) -> Event:
        self.sequence_id += 1
        snapshot = ProcessSnapshot(
            tank_level=plant.tank_level,
            valve_state="open" if plant.inlet_valve_open else "closed",
            pump_state="on" if plant.pump_on else "off",
            inlet_valve_state="open" if plant.inlet_valve_open else "closed",
            outlet_valve_state="open" if plant.outlet_valve_open else "closed",
            mode=plant.mode.name.lower(),
            power_source=plant.power_source.name.lower(),
            target_level=plant.target_level,
            high_level_limit=plant.high_level_limit,
        )
        event = Event(
            scenario_id=self.scenario_id,
            ground_truth=ground_truth,
            source=source,
            command=command,
            target=target,
            value=value,
            mode=plant.mode.name.lower(),
            process=snapshot,
            sequence_id=self.sequence_id,
            raw={"seed": self.seed, **(raw or {})},
        )
        self.store.append(event)
        return event


def plant_snapshot(plant: PlantState) -> dict[str, Any]:
    """Return JSON-friendly state for API/dashboard adapters."""
    state = asdict(plant)
    state["mode"] = plant.mode.name.lower()
    state["power_source"] = plant.power_source.name.lower()
    return state
