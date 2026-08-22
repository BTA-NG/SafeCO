from safeco.collector import EventCollector, plant_snapshot
from safeco.plant import OperatingMode, PlantState, PowerSource
from safeco.storage import EventStore


def test_collector_persists_full_plant_context(tmp_path):
    store = EventStore(tmp_path / "events.db")
    plant = PlantState(
        mode=OperatingMode.RECOVERY,
        power_source=PowerSource.GENERATOR,
        inlet_valve_open=True,
        outlet_valve_open=False,
    )
    collector = EventCollector(store, "recovery_01", seed=7)
    event = collector.record(
        plant,
        source="operator",
        command="mode_change",
        target="operating_mode",
    )
    assert event.sequence_id == 1
    assert event.process.power_source == "generator"
    assert event.process.mode == "recovery"
    assert event.process.outlet_valve_state == "closed"
    assert store.verify_chain() == (True, None)
    store.close()


def test_plant_snapshot_is_api_friendly():
    state = plant_snapshot(PlantState(mode=OperatingMode.RUNNING))
    assert state["mode"] == "running"
    assert state["power_source"] == "grid"
