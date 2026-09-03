from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from safeco.app import app
from safeco.events import Event, ProcessSnapshot
from safeco.storage import EventStore

client = TestClient(app)


@pytest.fixture()
def event_store(tmp_path):
    """Build a temporary event store for event-route tests."""
    database = tmp_path / "events.db"
    store = EventStore(database)
    app.state.store = store
    yield store
    store.close()


def test_event_list_returns_recent_rows(event_store) -> None:
    """The event feed should return the newest persisted events."""
    first = Event(
        scenario_id="normal_running_01",
        ground_truth="normal",
        source="scheduler",
        command="telemetry",
        target="tank",
        value=50.0,
        mode="running",
        process=ProcessSnapshot(50.0, "open", "off"),
        sequence_id=1,
    )
    second = Event(
        scenario_id="normal_running_01",
        ground_truth="normal",
        source="scheduler",
        command="write_coil",
        target="pump",
        value=1,
        mode="running",
        process=ProcessSnapshot(50.5, "open", "on"),
        sequence_id=2,
    )
    event_store.append(first)
    event_store.append(second)

    response = client.get("/api/events", params={"limit": 10})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert rows[0]["event_id"] == second.event_id


def test_event_detail_returned_by_event_id(event_store) -> None:
    """The detailed event endpoint should return one event row."""
    event = Event(
        scenario_id="attack_01",
        ground_truth="injection",
        source="attacker",
        command="write_coil",
        target="pump",
        value=1,
        mode="running",
        process=ProcessSnapshot(60.0, "closed", "on"),
        sequence_id=3,
    )
    event_store.append(event)

    response = client.get(f"/api/events/{event.event_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["event_id"] == event.event_id
    assert payload["scenario_id"] == "attack_01"


def test_event_detail_returns_404_for_missing_event(event_store) -> None:
    """A missing event id should return a 404."""
    response = client.get("/api/events/does-not-exist")
    assert response.status_code == 404


def test_events_after_returns_later_rows(event_store) -> None:
    """The after-event feed should return only events newer than the supplied id."""
    first = Event(
        scenario_id="normal_running_01",
        ground_truth="normal",
        source="scheduler",
        command="telemetry",
        target="tank",
        value=50.0,
        mode="running",
        process=ProcessSnapshot(50.0, "open", "off"),
        sequence_id=1,
    )
    second = Event(
        scenario_id="normal_running_01",
        ground_truth="normal",
        source="scheduler",
        command="telemetry",
        target="tank",
        value=51.0,
        mode="running",
        process=ProcessSnapshot(51.0, "open", "off"),
        sequence_id=2,
    )
    event_store.append(first)
    event_store.append(second)

    response = client.get(f"/api/events/after/{first.event_id}", params={"limit": 10})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["event_id"] == second.event_id
