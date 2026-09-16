"""Tests for the persistent SQLite alert store.

Written test-first: these define the AlertStore behaviour the API relies on —
deterministic upsert keyed by alert_id, acknowledgement that survives re-running
the detector, and filtered listing for the dashboard queue.
"""

from __future__ import annotations

from safeco.alert_store import AlertStore
from safeco.alerts import ReasonCode, build_alert


def sample_alert(event_id: str = "event-1", reason=ReasonCode.UNSAFE_PUMP_START):
    """Build a rendered alert with the evidence its template needs."""
    return build_alert(
        event_id,
        reason,
        {"tank_level": 55.2, "mode": "running"},
    )


def test_upsert_persists_and_lists_alert(tmp_path):
    store = AlertStore(tmp_path / "alerts.db")
    alert = sample_alert()
    store.upsert(alert)

    listed = store.list_alerts()
    assert len(listed) == 1
    assert listed[0]["alert_id"] == alert.alert_id
    assert listed[0]["reason_code"] == "unsafe_pump_start"
    assert listed[0]["acknowledged"] is False
    assert listed[0]["evidence"]["tank_level"] == 55.2
    store.close()


def test_upsert_is_idempotent_on_alert_id(tmp_path):
    store = AlertStore(tmp_path / "alerts.db")
    store.upsert(sample_alert())
    store.upsert(sample_alert())  # same event + reason -> same alert_id
    assert len(store.list_alerts()) == 1
    store.close()


def test_upsert_preserves_existing_acknowledgement(tmp_path):
    """Re-running the detector must not silently un-acknowledge an alert."""
    store = AlertStore(tmp_path / "alerts.db")
    alert = sample_alert()
    store.upsert(alert)
    store.acknowledge(alert.alert_id)

    store.upsert(alert)  # detector re-emits the same finding
    fetched = store.get(alert.alert_id)
    assert fetched["acknowledged"] is True
    store.close()


def test_acknowledge_unknown_alert_returns_false(tmp_path):
    store = AlertStore(tmp_path / "alerts.db")
    assert store.acknowledge("does-not-exist") is False
    store.close()


def test_get_unknown_alert_returns_none(tmp_path):
    store = AlertStore(tmp_path / "alerts.db")
    assert store.get("does-not-exist") is None
    store.close()


def test_list_filters_by_acknowledged(tmp_path):
    store = AlertStore(tmp_path / "alerts.db")
    a = sample_alert("event-1", ReasonCode.UNSAFE_PUMP_START)
    b = build_alert(
        "event-2",
        ReasonCode.TANK_ABOVE_HIGH_LIMIT,
        {"tank_level": 95.0, "high_level_limit": 90.0, "mode": "running"},
    )
    store.upsert(a)
    store.upsert(b)
    store.acknowledge(a.alert_id)

    unacked = store.list_alerts(acknowledged=False)
    assert [row["alert_id"] for row in unacked] == [b.alert_id]
    acked = store.list_alerts(acknowledged=True)
    assert [row["alert_id"] for row in acked] == [a.alert_id]
    store.close()


def test_list_orders_by_severity_then_alert_id(tmp_path):
    """The dashboard queue shows the most urgent alerts first."""
    store = AlertStore(tmp_path / "alerts.db")
    low = build_alert(
        "event-low",
        ReasonCode.LEVEL_OUT_OF_RANGE,
        {"tank_level": 150.0},
    )
    critical = build_alert(
        "event-crit",
        ReasonCode.TANK_ABOVE_HIGH_LIMIT,
        {"tank_level": 95.0, "high_level_limit": 90.0, "mode": "running"},
    )
    store.upsert(low)
    store.upsert(critical)

    listed = store.list_alerts()
    assert listed[0]["alert_id"] == critical.alert_id  # critical outranks low
    assert listed[0]["severity"] == "critical"
    store.close()


def test_acknowledgement_survives_reopen(tmp_path):
    database = tmp_path / "alerts.db"
    store = AlertStore(database)
    alert = sample_alert()
    store.upsert(alert)
    store.acknowledge(alert.alert_id)
    store.close()

    reopened = AlertStore(database)
    assert reopened.get(alert.alert_id)["acknowledged"] is True
    reopened.close()
