# tests/test_simulator.py
import pytest

from safeco.plant import OperatingMode, PowerSource, Register
from safeco.simulator import CommandRecord, PlantSimulator, ProtocolError


def test_apply_coil_starts_pump_and_records_command():
    sim = PlantSimulator()
    record = sim.apply_coil(Register.PUMP_COMMAND, 1)
    assert sim.read_coil(Register.PUMP_COMMAND) == 1
    assert record == CommandRecord(0, "pump", 1, "coil")


def test_unsafe_but_valid_pump_start_is_applied():
    sim = PlantSimulator()
    sim.apply_coil(Register.PUMP_COMMAND, 1)
    sim.apply_coil(Register.INLET_VALVE_COMMAND, 0)
    assert "pump_running_with_inlet_closed" in sim.state.validate()


def test_unknown_coil_address_raises_protocol_error():
    with pytest.raises(ProtocolError):
        PlantSimulator().apply_coil(99, 1)


def test_holding_setpoints_use_percent_encoding():
    sim = PlantSimulator()
    sim.apply_holding(Register.TARGET_LEVEL, 6500)
    assert sim.state.target_level == 65.0


def test_negative_percent_register_is_protocol_error():
    with pytest.raises(ProtocolError):
        PlantSimulator().apply_holding(Register.HIGH_LEVEL_LIMIT, -1)


def test_on_command_callback_fires():
    seen = []
    sim = PlantSimulator()
    sim.on_command = seen.append
    sim.apply_coil(Register.OUTLET_VALVE_COMMAND, 0)
    assert seen == [CommandRecord(2, "outlet_valve", 0, "coil")]


def test_mode_command_accepts_valid_modes_only():
    sim = PlantSimulator()
    sim.apply_holding(Register.MODE_COMMAND, int(OperatingMode.RUNNING))
    assert sim.state.mode is OperatingMode.RUNNING
    with pytest.raises(ProtocolError):
        sim.apply_holding(Register.MODE_COMMAND, 4)  # RECOVERY needs transfer sequence
    with pytest.raises(ProtocolError):
        sim.apply_holding(Register.MODE_COMMAND, 9)


def test_read_input_encodes_percent_times_hundred():
    sim = PlantSimulator()
    sim.state.tank_level = 55.25
    assert sim.read_input(Register.TANK_LEVEL) == 5525


def test_read_input_encodes_signed_flow():
    sim = PlantSimulator()
    sim.step(10)
    assert sim.read_input(Register.FLOW_RATE) == -35


def test_all_input_registers_round_trip():
    sim = PlantSimulator()
    sim.state.pump_on = True
    sim.state.inlet_valve_open = True
    sim.state.mode = OperatingMode.MAINTENANCE
    sim.state.power_source = PowerSource.GENERATOR
    assert sim.read_input(Register.PUMP_STATE) == 1
    assert sim.read_input(Register.INLET_VALVE_STATE) == 1
    assert sim.read_input(Register.OUTLET_VALVE_STATE) == 1
    assert sim.read_input(Register.OPERATING_MODE) == 3
    assert sim.read_input(Register.POWER_SOURCE) == 2


def test_holding_reads_echo_configured_values():
    sim = PlantSimulator()
    sim.apply_holding(Register.TARGET_LEVEL, 7000)
    sim.apply_holding(Register.HIGH_LEVEL_LIMIT, 9000)
    sim.apply_holding(Register.MODE_COMMAND, 2)
    assert [sim.read_holding(a) for a in (200, 201, 202)] == [7000, 9000, 2]
