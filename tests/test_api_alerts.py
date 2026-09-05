from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from safeco.alert_store import AlertStore
from safeco.alerts import ReasonCode, build_alert
from safeco.app import app

client = TestClient(app)


@pytest.fixture()
def alert_store(tmp_path):
    """Attach a temporary persistent alert store to the app."""
    store = AlertStore(tmp_path / "alerts.db")
    app.state.alert_store = store
    yield store
    store.close()


def _unsafe_pump_alert(event_id: str = "event-1"):
    return build_alert(
        event_id,
        ReasonCode.UNSAFE_PUMP_START,
        {"tank_level": 55.2, "mode": "running"},
    )


def test_alerts_endpoint_returns_persisted_alerts(alert_store) -> None:
    """The alert feed should serve alerts from the persistent store."""
    alert_store.upsert(_unsafe_pump_alert("event-1"))

    response = client.get("/api/alerts")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["reason_code"] == "unsafe_pump_start"
    assert payload[0]["acknowledged"] is False
    # Full contract shape so the dashboard can explain the alert.
    assert payload[0]["recommended_action"]
    assert payload[0]["evidence"]["tank_level"] == 55.2


def test_unacknowledged_alerts_filter(alert_store) -> None:
    """The unacknowledged route should filter the persisted alerts."""
    a = _unsafe_pump_alert("event-1")
    b = build_alert(
        "event-2",
        ReasonCode.TANK_ABOVE_HIGH_LIMIT,
        {"tank_level": 95.0, "high_level_limit": 90.0, "mode": "running"},
    )
    alert_store.upsert(a)
    alert_store.upsert(b)
    alert_store.acknowledge(a.alert_id)

    response = client.get("/api/alerts/unacknowledged")
    assert response.status_code == 200
    assert [item["alert_id"] for item in response.json()] == [b.alert_id]


def test_missing_alert_returns_404(alert_store) -> None:
    """A missing alert id should return a 404."""
    response = client.get("/api/alerts/not-found")
    assert response.status_code == 404
    assert response.json()["detail"] == "alert not found"


def test_acknowledge_alert_persists(alert_store) -> None:
    """Acknowledgement should persist in the store and survive a re-read."""
    alert = _unsafe_pump_alert("event-1")
    alert_store.upsert(alert)

    response = client.patch(f"/api/alerts/{alert.alert_id}/ack")
    assert response.status_code == 200
    payload = response.json()
    assert payload["alert_id"] == alert.alert_id
    assert payload["acknowledged"] is True
    assert alert_store.get(alert.alert_id)["acknowledged"] is True


def test_acknowledge_unknown_alert_returns_404(alert_store) -> None:
    """Acknowledging an unknown alert should 404, not report false success."""
    response = client.patch("/api/alerts/does-not-exist/ack")
    assert response.status_code == 404
