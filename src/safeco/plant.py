from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class OperatingMode(IntEnum):
    SHUTDOWN = 0
    STARTUP = 1
    RUNNING = 2
    MAINTENANCE = 3
    RECOVERY = 4


class PowerSource(IntEnum):
    OFF = 0
    GRID = 1
    GENERATOR = 2


class Register(IntEnum):
    # Read/write coils
    PUMP_COMMAND = 0
    INLET_VALVE_COMMAND = 1
    OUTLET_VALVE_COMMAND = 2

    # Read-only input registers (engineering value x 100 where needed)
    TANK_LEVEL = 100
    FLOW_RATE = 101
    PUMP_STATE = 102
    INLET_VALVE_STATE = 103
    OUTLET_VALVE_STATE = 104
    OPERATING_MODE = 105
    POWER_SOURCE = 106

    # Read/write holding registers
    TARGET_LEVEL = 200
    HIGH_LEVEL_LIMIT = 201
    MODE_COMMAND = 202


@dataclass
class PlantState:
    tank_level: float = 50.0
    flow_rate: float = 0.0
    pump_on: bool = False
    inlet_valve_open: bool = False
    outlet_valve_open: bool = True
    mode: OperatingMode = OperatingMode.SHUTDOWN
    power_source: PowerSource = PowerSource.GRID
    target_level: float = 70.0
    high_level_limit: float = 90.0

    def validate(self) -> list[str]:
        violations: list[str] = []
        if not 0.0 <= self.tank_level <= 100.0:
            violations.append("tank_level_out_of_physical_range")
        if self.target_level >= self.high_level_limit:
            violations.append("target_not_below_high_limit")
        if self.pump_on and not self.inlet_valve_open:
            violations.append("pump_running_with_inlet_closed")
        if self.pump_on and self.power_source == PowerSource.OFF:
            violations.append("pump_running_without_power")
        if (
            self.mode == OperatingMode.RUNNING
            and self.tank_level > self.high_level_limit
        ):
            violations.append("tank_above_high_level_limit")
        return violations

    def tick(self, seconds: float = 1.0) -> None:
        inflow = 1.0 if self.pump_on and self.inlet_valve_open else 0.0
        outflow = 0.35 if self.outlet_valve_open else 0.0
        self.flow_rate = inflow - outflow
        self.tank_level = min(
            100.0, max(0.0, self.tank_level + self.flow_rate * seconds)
        )

    def begin_grid_recovery(self) -> None:
        self.pump_on = False
        self.power_source = PowerSource.OFF
        self.mode = OperatingMode.RECOVERY

    def transfer_to_generator(self) -> None:
        if self.mode != OperatingMode.RECOVERY or self.pump_on:
            raise ValueError(
                "generator transfer requires recovery mode with pump stopped"
            )
        self.power_source = PowerSource.GENERATOR

    def resume_after_recovery(self) -> None:
        if self.mode != OperatingMode.RECOVERY:
            raise ValueError("plant is not in recovery mode")
        if self.power_source == PowerSource.OFF:
            raise ValueError("a power source must be available")
        self.inlet_valve_open = True
        self.mode = OperatingMode.STARTUP
