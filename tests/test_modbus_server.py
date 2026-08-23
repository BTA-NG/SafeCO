import asyncio

from pymodbus.client import AsyncModbusTcpClient

from safeco.modbus_server import ModbusPlantServer
from safeco.plant import Register
from safeco.simulator import PlantSimulator


def test_rejected_writes_are_recorded_not_raised_into_protocol():
    sim = PlantSimulator()
    server = ModbusPlantServer.__new__(ModbusPlantServer)
    server.simulator = sim
    server.rejected_writes = []
    server._on_holding_write(int(Register.MODE_COMMAND), 9)
    assert (int(Register.MODE_COMMAND), 9) in server.rejected_writes


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
