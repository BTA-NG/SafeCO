from __future__ import annotations

from safeco.events import Event, ProcessSnapshot


def test_event_list_returns_recent_rows(client, event_store) -> None:
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


def test_event_detail_returned_by_event_id(client, event_store) -> None:
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


def test_event_detail_returns_404_for_missing_event(client, event_store) -> None:
    """A missing event id should return a 404."""
    response = client.get("/api/events/does-not-exist")
    assert response.status_code == 404


def test_events_after_returns_later_rows(client, event_store) -> None:
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


def test_event_list_returns_event_contract_shape(client, event_store) -> None:
    """Event list responses must include properly deserialized Event fields.

    The process field must be a dict with ProcessSnapshot shape, not a JSON string.
    The value field must be the actual value, not a JSON string.
    """
    event = Event(
        scenario_id="normal_running_01",
        ground_truth="normal",
        source="scheduler",
        command="telemetry",
        target="tank",
        value=55.5,
        mode="running",
        process=ProcessSnapshot(55.5, "open", "on"),
        sequence_id=1,
    )
    event_store.append(event)

    response = client.get("/api/events", params={"limit": 10})
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1

    returned = events[0]
    # Verify value is deserialized, not a JSON string
    assert returned["value"] == 55.5
    assert isinstance(returned["value"], (int, float))

    # Verify process is a dict with ProcessSnapshot fields, not a JSON string
    assert isinstance(returned["process"], dict)
    assert returned["process"]["tank_level"] == 55.5
    assert returned["process"]["valve_state"] == "open"
    assert returned["process"]["pump_state"] == "on"

    # Verify all Event contract fields are present
    assert returned["event_id"] == event.event_id
    assert returned["timestamp"] == event.timestamp
    assert returned["scenario_id"] == "normal_running_01"
    assert returned["ground_truth"] == "normal"
    assert returned["source"] == "scheduler"
    assert returned["command"] == "telemetry"
    assert returned["target"] == "tank"
    assert returned["mode"] == "running"
    assert returned["sequence_id"] == 1


def test_event_detail_returns_event_contract_shape(client, event_store) -> None:
    """Individual event responses must deserialize value and process fields.

    This ensures the Event contract is honored for detail lookups.
    """
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
    returned = response.json()

    # Verify value is deserialized
    assert returned["value"] == 1
    assert isinstance(returned["value"], int)

    # Verify process is a dict, not a JSON string
    assert isinstance(returned["process"], dict)
    assert returned["process"]["tank_level"] == 60.0
    assert returned["process"]["valve_state"] == "closed"


def test_events_after_returns_event_contract_shape(client, event_store) -> None:
    """Events after a marker must also have deserialized Event fields.

    This ensures consistency across all event feed endpoints.
    """
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
    events = response.json()
    assert len(events) == 1

    returned = events[0]
    assert returned["event_id"] == second.event_id
    # Verify deserialization
    assert returned["value"] == 51.0
    assert isinstance(returned["process"], dict)
    assert returned["process"]["tank_level"] == 51.0
