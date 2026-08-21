import pytest

from safeco.plant import OperatingMode, PlantState, PowerSource, Register


def test_register_addresses_are_stable():
    assert Register.PUMP_COMMAND == 0
    assert Register.TANK_LEVEL == 100
    assert Register.TARGET_LEVEL == 200


def test_pump_with_closed_inlet_is_unsafe():
    plant = PlantState(pump_on=True, inlet_valve_open=False)
    assert "pump_running_with_inlet_closed" in plant.validate()


def test_legitimate_generator_recovery_is_valid():
    plant = PlantState(mode=OperatingMode.RUNNING, pump_on=True, inlet_valve_open=True)
    plant.begin_grid_recovery()
    plant.transfer_to_generator()
    plant.resume_after_recovery()
    assert plant.power_source == PowerSource.GENERATOR
    assert plant.mode == OperatingMode.STARTUP
    assert plant.validate() == []


def test_generator_transfer_rejects_running_pump():
    plant = PlantState(mode=OperatingMode.RECOVERY, pump_on=True)
    with pytest.raises(ValueError):
        plant.transfer_to_generator()


def test_tick_updates_visible_process_state():
    plant = PlantState(tank_level=50, pump_on=True, inlet_valve_open=True)
    plant.tick(seconds=2)
    assert plant.tank_level > 50
    assert plant.flow_rate > 0
