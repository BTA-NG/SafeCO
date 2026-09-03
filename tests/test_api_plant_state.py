from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from safeco.app import app
from safeco.events import Event, ProcessSnapshot
from safeco.storage import EventStore

client = TestClient(app)


@pytest.fixture()
def store_with_event(tmp_path):
    """Attach a temporary event store containing one process snapshot."""
    database = tmp_path / "plant_state.db"
    store = EventStore(database)
    app.state.store = store
    event = Event(
        scenario_id="maintenance_01",
        ground_truth="maintenance",
        source="scheduler",
        command="telemetry",
        target="tank",
        value=63.1,
        mode="maintenance",
        process=ProcessSnapshot(
            tank_level=63.1,
            valve_state="open",
            pump_state="on",
            inlet_valve_state="open",
            outlet_valve_state="open",
            mode="maintenance",
            power_source="generator",
            target_level=70.0,
            high_level_limit=90.0,
        ),
        sequence_id=1,
    )
    store.append(event)
    yield store
    store.close()


def test_plant_state_returns_latest_snapshot(store_with_event) -> None:
    """The plant-state endpoint should return the newest persisted process state."""
    response = client.get("/api/plant/state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario_id"] == "maintenance_01"
    assert payload["process"]["tank_level"] == 63.1
    assert payload["process"]["mode"] == "maintenance"
    assert payload["process"]["power_source"] == "generator"


def test_plant_state_handles_empty_store(tmp_path) -> None:
    """An empty store should return a safe no-data response."""
    database = tmp_path / "empty.db"
    store = EventStore(database)
    app.state.store = store
    try:
        response = client.get("/api/plant/state")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "no_data"
        assert payload["process"] is None
    finally:
        store.close()
