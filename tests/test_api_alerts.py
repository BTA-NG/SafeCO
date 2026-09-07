from __future__ import annotations

from safeco.app import app


def test_alerts_endpoint_returns_in_memory_alerts(client) -> None:
    """The alert feed should serve the in-memory alert state managed by the app."""
    app.state.alerts = [
        {"alert_id": "alert-1", "event_id": "event-1", "acknowledged": False},
        {"alert_id": "alert-2", "event_id": "event-2", "acknowledged": True},
    ]

    response = client.get("/api/alerts")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["alert_id"] == "alert-1"


def test_unacknowledged_alerts_filter_on_acknowledged_flag(client) -> None:
    """The unacknowledged route should filter the in-memory alerts."""
    app.state.alerts = [
        {"alert_id": "alert-1", "event_id": "event-1", "acknowledged": False},
        {"alert_id": "alert-2", "event_id": "event-2", "acknowledged": True},
    ]

    response = client.get("/api/alerts/unacknowledged")
    assert response.status_code == 200
    payload = response.json()
    assert [item["alert_id"] for item in payload] == ["alert-1"]


def test_missing_alert_returns_404(client) -> None:
    """A missing alert id should return a 404 until alert persistence exists."""
    app.state.alerts = []

    response = client.get("/api/alerts/not-found")
    assert response.status_code == 404
    assert response.json()["detail"] == "alert not found"


def test_acknowledge_alert_updates_in_memory_state(client) -> None:
    """The acknowledgement endpoint should update the in-memory alert state."""
    app.state.alerts = [
        {"alert_id": "test-alert", "event_id": "event-1", "acknowledged": False}
    ]

    response = client.patch("/api/alerts/test-alert/ack")
    assert response.status_code == 200
    payload = response.json()
    assert payload["alert_id"] == "test-alert"
    assert payload["acknowledged"] is True
    assert app.state.alerts[0]["acknowledged"] is True
