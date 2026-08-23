import asyncio

import pytest
from pymodbus.client import AsyncModbusTcpClient

from safeco.modbus_server import ModbusPlantServer, WatchedBlock
from safeco.plant import Register
from safeco.simulator import PlantSimulator, ProtocolError


def test_rejected_writes_are_recorded_and_reraised():
    sim = PlantSimulator()
    server = ModbusPlantServer.__new__(ModbusPlantServer)
    server.simulator = sim
    server.rejected_writes = []
    with pytest.raises(ProtocolError):
        server._on_holding_write(int(Register.MODE_COMMAND), 9)
    assert (int(Register.MODE_COMMAND), 9) in server.rejected_writes


def test_cross_family_write_is_recorded_as_rejected():
    sim = PlantSimulator()
    server = ModbusPlantServer.__new__(ModbusPlantServer)
    server.simulator = sim
    server.rejected_writes = []
    with pytest.raises(ProtocolError):
        server._on_coil_write(int(Register.TARGET_LEVEL), 1)
    assert (int(Register.TARGET_LEVEL), 1) in server.rejected_writes


async def _round_trip() -> None:
    sim = PlantSimulator(seed=42)
    # Low multiplier keeps per-tick physics drift (~0.04 level counts) far
    # inside the tolerance so the assertion cannot flake on tick timing.
    server = ModbusPlantServer(sim, port=15020, sim_seconds_per_real_second=1.0)
    server.start()
    try:
        await asyncio.sleep(0.5)  # let the socket bind and first ticks land
        client = AsyncModbusTcpClient("127.0.0.1", port=15020)
        assert await client.connect() is True
        response = await client.write_register(int(Register.MODE_COMMAND), 2)
        assert not response.isError()
        assert server.rejected_writes == []
        assert sim.state.mode.value == 2  # RUNNING reached the simulator
        state = await client.read_input_registers(int(Register.PUMP_STATE), count=1)
        level = await client.read_input_registers(int(Register.TANK_LEVEL), count=1)
        assert state.registers[0] in (0, 1)
        expected = round(sim.state.tank_level * 100)
        assert abs(level.registers[0] - expected) <= 100  # within one tick of drift
        client.close()
    finally:
        server.stop()


def test_modbus_round_trip_over_tcp():
    asyncio.run(_round_trip())


def test_rejected_write_is_never_stored_in_block():
    sim = PlantSimulator()
    server = ModbusPlantServer.__new__(ModbusPlantServer)
    server.simulator = sim
    server.rejected_writes = []
    block = WatchedBlock(0, [0] * 256, server._on_coil_write)
    with pytest.raises(ProtocolError):
        block.setValues(int(Register.TARGET_LEVEL), [1])
    assert block.getValues(int(Register.TARGET_LEVEL), 1) == [0]
    assert (int(Register.TARGET_LEVEL), 1) in server.rejected_writes


def test_accepted_write_is_stored_in_block():
    sim = PlantSimulator()
    server = ModbusPlantServer.__new__(ModbusPlantServer)
    server.simulator = sim
    server.rejected_writes = []
    block = WatchedBlock(0, [0] * 256, server._on_holding_write)
    block.setValues(int(Register.TARGET_LEVEL), [7500])
    assert block.getValues(int(Register.TARGET_LEVEL), 1) == [7500]
    assert server.rejected_writes == []


async def _rejected_write_round_trip() -> None:
    sim = PlantSimulator(seed=42)
    server = ModbusPlantServer(sim, port=15021, sim_seconds_per_real_second=1.0)
    server.start()
    try:
        await asyncio.sleep(0.5)  # let the socket bind and first ticks land
        client = AsyncModbusTcpClient("127.0.0.1", port=15021)
        assert await client.connect() is True
        response = await client.write_register(int(Register.TARGET_LEVEL), 7500)
        assert not response.isError()
        readback = await client.read_holding_registers(
            int(Register.TARGET_LEVEL), count=1
        )
        assert readback.registers[0] == 7500
        response = await client.write_register(int(Register.MODE_COMMAND), 2)
        assert not response.isError()
        readback = await client.read_holding_registers(
            int(Register.MODE_COMMAND), count=1
        )
        assert readback.registers[0] == 2
        response = await client.write_register(int(Register.MODE_COMMAND), 9)
        assert response.isError()
        readback = await client.read_holding_registers(
            int(Register.MODE_COMMAND), count=1
        )
        assert readback.registers[0] == 2
        assert (int(Register.MODE_COMMAND), 9) in server.rejected_writes
        response = await client.write_register(int(Register.TARGET_LEVEL), 8000)
        assert not response.isError()
        client.close()
    finally:
        server.stop()


def test_live_rejected_write_is_invisible_and_server_survives():
    asyncio.run(_rejected_write_round_trip())
