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
