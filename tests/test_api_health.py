from __future__ import annotations

from safeco.events import Event, ProcessSnapshot


def test_health_endpoint_reports_ok(client, event_store) -> None:
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
    event_store.append(event)

    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "available"
    assert payload["degraded_visibility"] is False


def test_health_endpoint_reports_degraded_visibility_when_no_events_exist(
    client,
    event_store,
) -> None:
    """If there is no recent event data, the API should report degraded visibility."""
    event_store.connection.execute("DELETE FROM events")
    event_store.connection.commit()

    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["degraded_visibility"] is True


def test_health_endpoint_reports_latest_event_timestamp(client, event_store) -> None:
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
    event_store.append(event)

    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["last_event_timestamp"] == event.timestamp
