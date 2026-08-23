from __future__ import annotations

import asyncio
import threading

from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext
try:
    from pymodbus.datastore import ModbusDeviceContext
except ImportError:  # pymodbus < 3.10 renamed slave->device
    from pymodbus.datastore import ModbusSlaveContext as ModbusDeviceContext
from pymodbus.server import ModbusTcpServer

from .simulator import PlantSimulator, ProtocolError

INPUT_ADDRESSES = (100, 101, 102, 103, 104, 105, 106)


class WatchedBlock(ModbusSequentialDataBlock):
    """Data block that forwards client writes to a callback."""

    def __init__(self, address: int, values: list[int], on_change=None) -> None:
        super().__init__(address, values)
        self.on_change = on_change

    def setValues(self, address, values):  # noqa: N802 - pymodbus API name
        super().setValues(address, values)
        if self.on_change is None:
            return
        for offset, value in enumerate(values):
            self.on_change(address + offset, value)


class ModbusPlantServer:
    """Expose one PlantSimulator over local Modbus TCP with a clock multiplier."""

    def __init__(self, simulator: PlantSimulator, host: str = "127.0.0.1",
                 port: int = 5020, sim_seconds_per_real_second: float = 60.0,
                 tick_interval: float = 0.1) -> None:
        self.simulator = simulator
        self.host, self.port = host, port
        self.tick_interval = tick_interval
        self.sim_step_seconds = tick_interval * sim_seconds_per_real_second
        self._stopping = False
        self.rejected_writes: list[tuple[int, int]] = []
        co = WatchedBlock(0, [0] * 256, self._on_coil_write)
        hr = WatchedBlock(0, [0] * 256, self._on_holding_write)
        di = ModbusSequentialDataBlock(0, [0] * 256)
        ir = ModbusSequentialDataBlock(0, [0] * 256)
        try:
            # zero_mode keeps client addresses identical to Register enum values
            device = ModbusDeviceContext(di=di, co=co, hr=hr, ir=ir, zero_mode=True)
        except TypeError:  # context flavors without one-based-address emulation
            device = ModbusDeviceContext(di=di, co=co, hr=hr, ir=ir)
        try:
            self.context = ModbusServerContext(device, single=True)
        except TypeError:  # pymodbus keyword form
            self.context = ModbusServerContext(slaves=device, single=True)
        self._ir_block = ir

    def _on_coil_write(self, address: int, value: int) -> None:
        try:
            self.simulator.apply_coil(address, value)
        except ProtocolError:
            self.rejected_writes.append((address, value))

    def _on_holding_write(self, address: int, value: int) -> None:
        try:
            self.simulator.apply_holding(address, value)
        except ProtocolError:
            self.rejected_writes.append((address, value))

    def _tick(self) -> None:
        self.simulator.step(self.sim_step_seconds)
        for addr in INPUT_ADDRESSES:
            self._ir_block.setValues(addr, [self.simulator.read_input(addr)])

    async def _serve(self) -> None:
        server = ModbusTcpServer(context=self.context, address=(self.host, self.port))
        if callable(getattr(server, "serving", None)):
            await server.serving()
        else:  # pymodbus < 3.10: bind here; its serving Future ends at shutdown()
            await server.listen()
        while not self._stopping:
            await asyncio.sleep(self.tick_interval)
            self._tick()
        await server.shutdown()

    def start(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=lambda: (asyncio.set_event_loop(self._loop),
                            self._loop.run_until_complete(self._serve())),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stopping = True
        self._thread.join(timeout=5)
        try:
            pending = [t for t in asyncio.all_tasks(self._loop) if not t.done()]
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True))
        except RuntimeError:
            pass
        self._loop.close()
