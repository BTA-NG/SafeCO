import pytest

from safeco.events import Event, ProcessSnapshot
from safeco.storage import EventStore


def sample_event(sequence_id: int = 1) -> Event:
    return Event(
        scenario_id="normal_running_01",
        ground_truth="normal",
        source="scheduler",
        command="telemetry",
        target="tank",
        value=55.2,
        mode="running",
        process=ProcessSnapshot(55.2, "open", "on"),
        sequence_id=sequence_id,
    )


def test_event_store_appends_and_verifies(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.append(sample_event())
    store.append(sample_event(2))
    assert len(store.list_events()) == 2
    assert store.verify_chain() == (True, None)
    store.close()


def test_event_store_detects_tampering(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.append(sample_event())
    store.connection.execute("UPDATE events SET target = 'pump'")
    store.connection.commit()
    assert store.verify_chain()[0] is False
    store.close()


def test_event_queries_support_scenario_filter_and_catch_up(tmp_path):
    store = EventStore(tmp_path / "events.db")
    first = sample_event()
    second = Event(
        scenario_id="attack_01",
        ground_truth="injection",
        source="attacker",
        command="write_coil",
        target="pump",
        value=1,
        mode="running",
        process=ProcessSnapshot(55.2, "closed", "on"),
        sequence_id=2,
    )
    third = Event(
        scenario_id="normal_running_01",
        ground_truth="normal",
        source="scheduler",
        command="telemetry",
        target="tank",
        value=55.5,
        mode="running",
        process=ProcessSnapshot(55.5, "open", "on"),
        sequence_id=3,
    )
    for event in (first, second, third):
        store.append(event)

    normal = store.list_events(scenario_id="normal_running_01")
    assert [row["event_id"] for row in normal] == [third.event_id, first.event_id]
    replay = store.events_after(first.event_id)
    assert [row["event_id"] for row in replay] == [second.event_id, third.event_id]
    assert store.events_after(first.event_id, limit=1)[0]["event_id"] == second.event_id
    with pytest.raises(KeyError):
        store.events_after("missing-event")
    store.close()
