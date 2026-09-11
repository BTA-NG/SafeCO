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
        plant: PlantState | None,
        *,
        source: str,
        command: str,
        target: str,
        value: Any = None,
        ground_truth: str = "normal",
        raw: dict[str, Any] | None = None,
        process: ProcessSnapshot | None = None,
    ) -> Event:
        """Build an ``Event`` and append it to the store.

        Args:
            plant: Current ``PlantState`` snapshot, used to derive the
                ``ProcessSnapshot`` when ``process`` is not supplied.
            source: Event originator (e.g. ``"scheduler"``).
            command: Command name (e.g. ``"write_coil"``).
            target: Target register name.
            value: Optional value written.
            ground_truth: Ground-truth label for this event.
            raw: Optional extra metadata merged into the event's ``raw`` dict.
            process: Pre-built observer ``ProcessSnapshot`` override. When
                supplied, it replaces the state derived from ``plant``.

        Returns:
            The persisted ``Event`` with its assigned ``event_id``.

        Raises:
            ValueError: If neither ``plant`` nor ``process`` provides state.

        """
        if process is None:
            if plant is None:
                raise ValueError(
                    "record() requires either plant state or a process snapshot"
                )
            process = ProcessSnapshot(
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
        self.sequence_id += 1
        event = Event(
            scenario_id=self.scenario_id,
            ground_truth=ground_truth,
            source=source,
            command=command,
            target=target,
            value=value,
            mode=process.mode,
            process=process,
            sequence_id=self.sequence_id,
            raw={"seed": self.seed, **(raw or {})},
        )
        self.store.append(event)
        return event

    def record_simulator_command(
        self,
        simulator: PlantSimulator | None,
        command: CommandRecord,
        *,
        source: str = "scheduler",
        ground_truth: str = "normal",
        raw: dict[str, Any] | None = None,
        process: ProcessSnapshot | None = None,
    ) -> Event:
        """Persist one simulator command with its resulting process state.

        Args:
            simulator: Simulator providing the current state. May be ``None``
                when ``process`` carries the observer snapshot instead.
            command: The recorded command to persist.
            source: Event originator (e.g. ``"scheduler"``).
            ground_truth: Ground-truth label for this event.
            raw: Optional extra metadata merged into the event's ``raw`` dict.
            process: Pre-built observer ``ProcessSnapshot`` override, used
                when the caller has an observed snapshot to attach.

        Returns:
            The persisted ``Event`` with its assigned ``event_id``.

        """
        plant = simulator.state if simulator is not None else None
        return self.record(
            plant,
            source=source,
            command=f"write_{command.kind}",
            target=command.target,
            value=command.value,
            ground_truth=ground_truth,
            raw={"address": command.address, "kind": command.kind, **(raw or {})},
            process=process,
        )


def plant_snapshot(plant: PlantState) -> dict[str, Any]:
    """Return JSON-friendly state for API/dashboard adapters."""
    state = asdict(plant)
    state["mode"] = plant.mode.name.lower()
    state["power_source"] = plant.power_source.name.lower()
    return state
