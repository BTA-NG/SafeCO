"""Sample integration runner for SafeCO.

Provides deterministic demo workflows that wire the simulator, collector,
and storage together, plus a CLI entry point for quick validation.
"""

from __future__ import annotations

import argparse

from .collector import EventCollector
from .plant import OperatingMode, PlantState, Register
from .simulator import PlantSimulator
from .storage import EventStore


def run_sample(database: str = "data/safeco.db", seed: int = 42) -> int:
    """Generate a small deterministic Adupe run for integration and demos."""
    store = EventStore(database)
    plant = PlantState(
        tank_level=50.0,
        inlet_valve_open=True,
        outlet_valve_open=True,
        mode=OperatingMode.RUNNING,
    )
    collector = EventCollector(store, "normal_running_sample", seed=seed)
    collector.record(
        plant,
        source="scheduler",
        command="telemetry",
        target="tank",
    )
    plant.pump_on = True
    plant.tick(seconds=5)
    collector.record(
        plant,
        source="scheduler",
        command="write_coil",
        target="pump",
        value=1,
    )
    valid, event_id = store.verify_chain()
    events = store.list_events(limit=2)
    print(f"recorded={len(events)} chain_valid={valid} invalid_event={event_id}")
    store.close()
    return 0 if valid else 1


def run_simulator_sample(
    database: str = "data/safeco.db",
    seed: int = 42,
    detector=None,
) -> int:
    """Persist deterministic simulator commands and notify a detector adapter."""
    store = EventStore(database)
    simulator = PlantSimulator(seed=seed)
    collector = EventCollector(store, "startup_integration_01", seed=seed)

    def collect(command) -> None:
        event = collector.record_simulator_command(simulator, command)
        if detector is not None:
            detector(event)

    simulator.on_command = collect
    simulator.apply_coil(Register.INLET_VALVE_COMMAND, 1)
    simulator.apply_coil(Register.PUMP_COMMAND, 1)
    simulator.apply_holding(Register.MODE_COMMAND, int(OperatingMode.RUNNING))
    simulator.step(seconds=5)

    valid, _ = store.verify_chain()
    store.close()
    return 0 if valid else 1


def main() -> int:
    """Parse CLI arguments and run the sample integration workflow.

    Returns:
        Exit code — ``0`` if the hash chain is valid, ``1`` otherwise.

    """
    parser = argparse.ArgumentParser(description="Run a deterministic SafeCO sample")
    parser.add_argument("--database", default="data/safeco.db")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    return run_sample(args.database, args.seed)


if __name__ == "__main__":
    raise SystemExit(main())
