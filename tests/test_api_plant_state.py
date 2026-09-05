from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from safeco.app import app
from safeco.events import Event, ProcessSnapshot

client = TestClient(app)


@pytest.fixture()
def store_with_event(api_store):
    """Seed the shared per-test store with one process snapshot."""
    store = api_store
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
    return store


def test_plant_state_returns_latest_snapshot(store_with_event) -> None:
    """The plant-state endpoint should return the newest persisted process state."""
    response = client.get("/api/plant/state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["scenario_id"] == "maintenance_01"
    assert payload["process"]["tank_level"] == 63.1
    assert payload["process"]["mode"] == "maintenance"
    assert payload["process"]["power_source"] == "generator"


def test_plant_state_handles_empty_store(api_store) -> None:
    """An empty store should return a safe no-data response."""
    response = client.get("/api/plant/state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "no_data"
    assert payload["process"] is None


def test_plant_state_returns_full_event_contract_shape(store_with_event) -> None:
    """Plant state should return the full Event contract, not just process dict."""
    response = client.get("/api/plant/state")
    assert response.status_code == 200
    payload = response.json()

    # Verify all Event contract fields are present
    assert "event_id" in payload
    assert "timestamp" in payload
    assert "scenario_id" in payload
    assert "ground_truth" in payload
    assert "source" in payload
    assert "command" in payload
    assert "target" in payload
    assert "value" in payload
    assert "mode" in payload
    assert "sequence_id" in payload
    assert "process" in payload

    # Verify process is a dict with ProcessSnapshot fields
    assert isinstance(payload["process"], dict)
    assert payload["process"]["tank_level"] == 63.1
    assert payload["process"]["valve_state"] == "open"
    assert payload["process"]["pump_state"] == "on"

    # Verify Event fields have correct values
    assert payload["ground_truth"] == "maintenance"
    assert payload["source"] == "scheduler"
    assert payload["command"] == "telemetry"
    assert payload["scenario_id"] == "maintenance_01"
    assert payload["sequence_id"] == 1
