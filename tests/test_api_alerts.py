from __future__ import annotations

from fastapi.testclient import TestClient

from safeco.app import app

client = TestClient(app)


def test_alerts_endpoint_returns_empty_list() -> None:
    """The alert feed is placeholder-backed for the current milestone."""
    response = client.get("/api/alerts")
    assert response.status_code == 200
    assert response.json() == []


def test_unacknowledged_alerts_returns_empty_list() -> None:
    """Unacknowledged alerts are currently placeholder-backed."""
    response = client.get("/api/alerts/unacknowledged")
    assert response.status_code == 200
    assert response.json() == []


def test_missing_alert_returns_404() -> None:
    """A missing alert id should return a 404 until alert persistence exists."""
    response = client.get("/api/alerts/not-found")
    assert response.status_code == 404
    assert response.json()["detail"] == "alert not found"


def test_acknowledge_alert_returns_acknowledged_payload() -> None:
    """The acknowledgement endpoint should confirm a successful update."""
    response = client.patch("/api/alerts/test-alert/ack")
    assert response.status_code == 200
    payload = response.json()
    assert payload["alert_id"] == "test-alert"
    assert payload["acknowledged"] is True
