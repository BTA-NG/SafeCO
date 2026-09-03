from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from safeco.app import app
from safeco.events import Event, ProcessSnapshot
from safeco.storage import EventStore

client = TestClient(app)


@pytest.fixture()
def populated_store(tmp_path):
    """Attach a temporary SQLite store to the app for route tests."""
    database = tmp_path / "health.db"
    store = EventStore(database)
    app.state.store = store
    yield store
    store.close()


def test_health_endpoint_reports_ok(populated_store) -> None:
    """The health endpoint should report the service as available."""
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "available"
    assert payload["degraded_visibility"] is False


def test_health_endpoint_reports_latest_event_timestamp(populated_store) -> None:
    """The health endpoint should include the newest persisted event time."""
    event = Event(
        scenario_id="normal_running_01",
        ground_truth="normal",
        source="scheduler",
        command="telemetry",
        target="tank",
        value=55.2,
        mode="running",
        process=ProcessSnapshot(55.2, "open", "on"),
        sequence_id=1,
    )
    populated_store.append(event)

    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["last_event_timestamp"] == event.timestamp
