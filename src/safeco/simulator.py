from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from .plant import OperatingMode, PlantState, Register


class ProtocolError(ValueError):
    """A write/read that is invalid under the documented plant contract."""


@dataclass(frozen=True)
class CommandRecord:
    address: int
    target: str
    value: float | int
    kind: str


COIL_TARGETS = {
    Register.PUMP_COMMAND: "pump",
    Register.INLET_VALVE_COMMAND: "inlet_valve",
    Register.OUTLET_VALVE_COMMAND: "outlet_valve",
}
HOLDING_TARGETS = {
    Register.TARGET_LEVEL: "level_setpoint",
    Register.HIGH_LEVEL_LIMIT: "high_level_limit",
    Register.MODE_COMMAND: "mode",
}


class PlantSimulator:
    """Deterministic process model bound to the documented Adupe register map."""

    def __init__(self, state: PlantState | None = None, *, seed: int = 42,
                 noise_scale: float = 0.0) -> None:
        self.state = state if state is not None else PlantState()
        self.rng = random.Random(seed)
        self.noise_scale = noise_scale
        self.commands: list[CommandRecord] = []
        self.on_command: Callable[[CommandRecord], None] | None = None

    def _record(self, record: CommandRecord) -> CommandRecord:
        self.commands.append(record)
        if self.on_command:
            self.on_command(record)
        return record

    def apply_coil(self, address: int, value: int) -> CommandRecord:
        try:
            target = COIL_TARGETS[Register(address)]
        except ValueError as exc:
            raise ProtocolError(f"unknown coil address {address}") from exc
        on = bool(value)
        if target == "pump":
            self.state.pump_on = on
        elif target == "inlet_valve":
            self.state.inlet_valve_open = on
        else:
            self.state.outlet_valve_open = on
        return self._record(CommandRecord(address, target, int(on), "coil"))

    def apply_holding(self, address: int, value: int) -> CommandRecord:
        try:
            target = HOLDING_TARGETS[Register(address)]
        except ValueError as exc:
            raise ProtocolError(f"unknown holding address {address}") from exc
        if target == "mode":
            return self._record(self._apply_mode(value))
        if not 0 <= value <= 10_000:
            raise ProtocolError("percent registers encode 0.00..100.00 as 0..10000")
        percent = value / 100.0
        if target == "level_setpoint":
            self.state.target_level = percent
        else:
            self.state.high_level_limit = percent
        return self._record(CommandRecord(address, target, percent, "holding"))

    # Completed in Task 2; stubbed here so the module imports.
    def _apply_mode(self, raw: int) -> CommandRecord:
        raise NotImplementedError

    def read_coil(self, address: int) -> int:
        try:
            target = COIL_TARGETS[Register(address)]
        except ValueError as exc:
            raise ProtocolError(f"unknown coil address {address}") from exc
        states = {
            "pump": self.state.pump_on,
            "inlet_valve": self.state.inlet_valve_open,
            "outlet_valve": self.state.outlet_valve_open,
        }
        return int(states[target])

    def read_holding(self, address: int) -> int:
        raise NotImplementedError  # Task 2

    def read_input(self, address: int) -> int:
        raise NotImplementedError  # Task 2

    def step(self, seconds: float = 1.0) -> list[str]:
        """Advance physics deterministically; returns current invariant violations."""
        self.state.tick(seconds)
        return self.state.validate()

    def snapshot(self) -> dict:
        from .collector import plant_snapshot

        return plant_snapshot(self.state)
