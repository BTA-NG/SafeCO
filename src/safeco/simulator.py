"""Deterministic Modbus TCP simulator for the Adupe Municipal Water Station.

Provides register-level command application over a frozen Register map
with seeded random telemetry noise. The simulator enforces advisory-only
semantics: unsafe-but-protocol-valid commands are applied and recorded,
never silently dropped.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from .plant import OperatingMode, PlantState, Register


class ProtocolError(ValueError):
    """A write or read that is invalid under the documented plant contract."""


@dataclass(frozen=True)
class CommandRecord:
    """One recorded command applied to the plant simulator.

    Attributes:
        address: Raw Modbus register address that was written.
        target: Human-readable target name (e.g. ``"pump"``, ``"mode"``).
        value: Effective value after encoding (bool for coils, percent for
            holdings, raw int for mode).
        kind: Register family — ``"coil"`` or ``"holding"``.

    """

    address: int
    target: str
    value: float | int
    kind: str


def _resolve_target(mapping: dict, address: int, family: str) -> str:
    """Resolve a raw Modbus address to a human-readable target name.

    Args:
        mapping: Register-to-target lookup table (``COIL_TARGETS`` or
            ``HOLDING_TARGETS``).
        address: Raw integer address from the Modbus request.
        family: ``"coil"`` or ``"holding"`` — used only in error messages.

    Returns:
        The target name string from the mapping.

    Raises:
        ProtocolError: If address is not a valid Register member or does
            not belong to the given family.

    """
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
    """Deterministic process model bound to the documented Adupe register map.

    Commands are applied against a ``PlantState`` instance. Each coil or
    holding write mutates the state and is recorded as a ``CommandRecord``.
    Telemetry noise is applied only during ``read_input`` calls and does
    not affect the underlying state.

    Args:
        state: Optional pre-built ``PlantState``. A fresh default state is
            created when ``None``.
        seed: Seed for the internal random number generator.
        noise_scale: Standard deviation of Gaussian noise added to
            ``read_input`` telemetry. Defaults to ``0.0`` (no noise).

    """

    def __init__(
        self,
        state: PlantState | None = None,
        *,
        seed: int = 42,
        noise_scale: float = 0.0,
    ) -> None:
        """See class docstring for parameter descriptions."""
        self.state = state if state is not None else PlantState()
        self.rng = random.Random(seed)
        self.noise_scale = noise_scale
        self.commands: list[CommandRecord] = []
        self.on_command: Callable[[CommandRecord], None] | None = None

    def _record(self, record: CommandRecord) -> CommandRecord:
        """Append a command to the log and notify the ``on_command`` callback."""
        self.commands.append(record)
        if self.on_command:
            self.on_command(record)
        return record

    def apply_coil(self, address: int, value: int) -> CommandRecord:
        """Apply a single coil write to the plant model.

        Args:
            address: Register address — must be a member of ``COIL_TARGETS``.
            value: Coil value (``0`` for off, ``1`` for on).

        Returns:
            The recorded ``CommandRecord``.

        Raises:
            ProtocolError: If address is not a known coil register.

        """
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
        """Apply a single holding-register write to the plant model.

        Percent registers encode values as raw integers 0–10000 (i.e. the
        real percentage multiplied by 100). Mode writes are routed through
        ``_apply_mode`` and are only accepted for non-RECOVERY transitions.

        Args:
            address: Register address — must be a member of
                ``HOLDING_TARGETS``.
            value: Raw register value (percent × 100 for setpoints,
                operating mode int for MODE_COMMAND).

        Returns:
            The recorded ``CommandRecord``.

        Raises:
            ProtocolError: If address is unknown, the value is out of
                range, or the mode is RECOVERY / invalid.

        """
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
        """Validate and apply an operating-mode transition.

        RECOVERY mode cannot be entered directly; it requires the
        grid-loss transfer sequence on ``PlantState``.

        Args:
            raw: Raw integer mode value from the holding register.

        Returns:
            A ``CommandRecord`` describing the mode change.

        Raises:
            ProtocolError: If ``raw`` is not a valid ``OperatingMode`` or
                is ``RECOVERY``.

        """
        try:
            requested = OperatingMode(raw)
        except ValueError as exc:
            raise ProtocolError(f"unknown operating mode {raw}") from exc
        if requested is OperatingMode.RECOVERY:
            raise ProtocolError("recovery requires the grid-loss transfer sequence")
        self.state.mode = requested
        return CommandRecord(Register.MODE_COMMAND, "mode", raw, "holding")

    def read_coil(self, address: int) -> int:
        """Read the current value of a coil register.

        Args:
            address: Register address — must be a member of ``COIL_TARGETS``.

        Returns:
            ``1`` if the coil target is active, ``0`` otherwise.

        Raises:
            ProtocolError: If address is not a known coil register.

        """
        target = _resolve_target(COIL_TARGETS, address, "coil")
        states = {
            "pump": self.state.pump_on,
            "inlet_valve": self.state.inlet_valve_open,
            "outlet_valve": self.state.outlet_valve_open,
        }
        return int(states[target])

    def read_holding(self, address: int) -> int:
        """Read the current value of a holding register.

        Percent values are encoded back to raw integers (percent × 100).

        Args:
            address: Register address — must be a member of
                ``HOLDING_TARGETS``.

        Returns:
            Raw register value (percent × 100 for setpoints, mode int
            for MODE_COMMAND).

        Raises:
            ProtocolError: If address is unknown or not a holding register.

        """
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
        """Read a telemetry input register, with optional noise applied.

        Gaussian noise scaled by ``noise_scale`` is added to analog
        readings (tank level and flow rate). Digital readings (pump
        state, valve states, mode, power source) are noise-free.

        Args:
            address: Register address — must be a member of the input
                register set (TANK_LEVEL through POWER_SOURCE).

        Returns:
            Raw register value (percent × 100 for analog readings,
            int for digital/mode readings).

        Raises:
            ProtocolError: If address is unknown or not an input register.

        """
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
        """Return a JSON-friendly snapshot of the current plant state.

        Delegates to ``collector.plant_snapshot``. The returned dict
        contains tank level, flow rate, valve/pump states, operating
        mode, power source, setpoints, and limit values.
        """
        from .collector import plant_snapshot

        return plant_snapshot(self.state)
