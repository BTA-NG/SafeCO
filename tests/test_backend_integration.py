import json

from safeco.runtime import run_simulator_sample
from safeco.storage import EventStore


def test_simulator_commands_flow_to_store_and_detector(tmp_path):
    database = tmp_path / "integration.db"
    detected = []

    assert run_simulator_sample(database, seed=42, detector=detected.append) == 0

    store = EventStore(database)
    rows = list(reversed(store.list_events()))
    assert len(rows) == 3
    assert [row["sequence_id"] for row in rows] == [1, 2, 3]
    assert [row["target"] for row in rows] == ["inlet_valve", "pump", "mode"]
    assert json.loads(rows[1]["process_json"])["pump_state"] == "on"
    assert json.loads(rows[2]["raw_json"]) == {
        "address": 202,
        "kind": "holding",
        "seed": 42,
    }
    assert store.verify_chain() == (True, None)
    assert [event.event_id for event in detected] == [row["event_id"] for row in rows]
    store.close()
