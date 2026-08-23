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


def _resolve_target(mapping: dict, address: int, family: str) -> str:
    try:
        reg = Register(address)
    except ValueError as exc:
        raise ProtocolError(f"unknown {family} address {address}") from exc
    target = mapping.get(reg)
    if target is None:
        raise ProtocolError(f"{reg.name} is not a {family} register")
    return target


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
        target = _resolve_target(COIL_TARGETS, address, "coil")
        on = bool(value)
        if target == "pump":
            self.state.pump_on = on
        elif target == "inlet_valve":
            self.state.inlet_valve_open = on
        else:
            self.state.outlet_valve_open = on
        return self._record(CommandRecord(address, target, int(on), "coil"))

    def apply_holding(self, address: int, value: int) -> CommandRecord:
        target = _resolve_target(HOLDING_TARGETS, address, "holding")
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

    def _apply_mode(self, raw: int) -> CommandRecord:
        try:
            requested = OperatingMode(raw)
        except ValueError as exc:
            raise ProtocolError(f"unknown operating mode {raw}") from exc
        if requested is OperatingMode.RECOVERY:
            raise ProtocolError("recovery requires the grid-loss transfer sequence")
        self.state.mode = requested
        return CommandRecord(Register.MODE_COMMAND, "mode", raw, "holding")

    def read_coil(self, address: int) -> int:
        target = _resolve_target(COIL_TARGETS, address, "coil")
        states = {
            "pump": self.state.pump_on,
            "inlet_valve": self.state.inlet_valve_open,
            "outlet_valve": self.state.outlet_valve_open,
        }
        return int(states[target])

    def read_holding(self, address: int) -> int:
        try:
            reg = Register(address)
        except ValueError as exc:
            raise ProtocolError(f"unknown holding address {address}") from exc
        match reg:
            case Register.TARGET_LEVEL:
                return round(self.state.target_level * 100)
            case Register.HIGH_LEVEL_LIMIT:
                return round(self.state.high_level_limit * 100)
            case Register.MODE_COMMAND:
                return int(self.state.mode)
        raise ProtocolError(f"{reg.name} is not a holding register")

    def read_input(self, address: int) -> int:
        try:
            reg = Register(address)
        except ValueError as exc:
            raise ProtocolError(f"unknown input address {address}") from exc
        noise = self.rng.gauss(0.0, self.noise_scale)
        match reg:
            case Register.TANK_LEVEL:
                return round((self.state.tank_level + noise) * 100)
            case Register.FLOW_RATE:
                return round((self.state.flow_rate + noise) * 100)
            case Register.PUMP_STATE:
                return int(self.state.pump_on)
            case Register.INLET_VALVE_STATE:
                return int(self.state.inlet_valve_open)
            case Register.OUTLET_VALVE_STATE:
                return int(self.state.outlet_valve_open)
            case Register.OPERATING_MODE:
                return int(self.state.mode)
            case Register.POWER_SOURCE:
                return int(self.state.power_source)
        raise ProtocolError(f"{reg.name} is not an input register")

    def step(self, seconds: float = 1.0) -> list[str]:
        """Advance physics deterministically; returns current invariant violations."""
        self.state.tick(seconds)
        return self.state.validate()

    def snapshot(self) -> dict:
        from .collector import plant_snapshot

        return plant_snapshot(self.state)
