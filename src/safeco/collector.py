"""Event collector bridging the plant simulator to the persisted event store.

Translates ``PlantState`` snapshots and ``CommandRecord`` results into
the shared ``Event`` contract and appends them to an ``EventStore``.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from .events import Event, ProcessSnapshot
from .plant import PlantState
from .storage import EventStore

if TYPE_CHECKING:
    from .simulator import CommandRecord, PlantSimulator


class EventCollector:
    """Translate plant state/commands into the shared persisted event contract."""

    def __init__(
        self, store: EventStore, scenario_id: str, seed: int | None = None
    ) -> None:
        """Initialise the collector with a store and scenario context.

        Args:
            store: The ``EventStore`` to persist events to.
            scenario_id: Registry key for the running scenario.
            seed: Optional RNG seed, stored in every event's ``raw`` metadata.

        """
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
        """Build an ``Event`` from the current plant state and append it to the store.

        Args:
            plant: Current ``PlantState`` snapshot.
            source: Event originator (e.g. ``"scheduler"``).
            command: Command name (e.g. ``"write_coil"``).
            target: Target register name.
            value: Optional value written.
            ground_truth: Ground-truth label for this event.
            raw: Optional extra metadata merged into the event's ``raw`` dict.

        Returns:
            The persisted ``Event`` with its assigned ``event_id``.

        """
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

    def record_simulator_command(
        self,
        simulator: PlantSimulator,
        command: CommandRecord,
        *,
        source: str = "scheduler",
        ground_truth: str = "normal",
        raw: dict[str, Any] | None = None,
    ) -> Event:
        """Persist one simulator command with its resulting process state."""
        return self.record(
            simulator.state,
            source=source,
            command=f"write_{command.kind}",
            target=command.target,
            value=command.value,
            ground_truth=ground_truth,
            raw={"address": command.address, "kind": command.kind, **(raw or {})},
        )


def plant_snapshot(plant: PlantState) -> dict[str, Any]:
    """Return JSON-friendly state for API/dashboard adapters."""
    state = asdict(plant)
    state["mode"] = plant.mode.name.lower()
    state["power_source"] = plant.power_source.name.lower()
    return state
