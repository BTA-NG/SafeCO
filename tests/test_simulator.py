# tests/test_simulator.py
import pytest

from safeco.plant import OperatingMode, Register
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
