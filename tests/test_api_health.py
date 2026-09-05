from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from safeco.app import app
from safeco.events import Event, ProcessSnapshot

client = TestClient(app)


@pytest.fixture()
def populated_store(api_store):
    """Alias the shared per-test store injected by the autouse fixture."""
    return api_store


def test_health_endpoint_reports_ok(populated_store) -> None:
    """The health endpoint should report the service as available."""
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
    assert payload["status"] == "ok"
    assert payload["database"] == "available"
    assert payload["degraded_visibility"] is False


def test_health_endpoint_reports_degraded_visibility_when_no_events_exist(
    populated_store,
) -> None:
    """If there is no recent event data, the API should report degraded visibility."""
    populated_store.connection.execute("DELETE FROM events")
    populated_store.connection.commit()

    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["degraded_visibility"] is True


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
