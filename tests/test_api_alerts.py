from __future__ import annotations

from safeco.alerts import ReasonCode, build_alert


def _unsafe_pump_alert(event_id: str = "event-1"):
    return build_alert(
        event_id,
        ReasonCode.UNSAFE_PUMP_START,
        {"tank_level": 55.2, "mode": "running"},
    )


def test_alerts_endpoint_returns_persisted_alerts(client, alert_store) -> None:
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


def test_unacknowledged_alerts_filter(client, alert_store) -> None:
    """?acknowledged=false should return only the pending alerts."""
    a = _unsafe_pump_alert("event-1")
    b = build_alert(
        "event-2",
        ReasonCode.TANK_ABOVE_HIGH_LIMIT,
        {"tank_level": 95.0, "high_level_limit": 90.0, "mode": "running"},
    )
    alert_store.upsert(a)
    alert_store.upsert(b)
    alert_store.acknowledge(a.alert_id)

    response = client.get("/api/alerts", params={"acknowledged": "false"})
    assert response.status_code == 200
    assert [item["alert_id"] for item in response.json()] == [b.alert_id]


def test_acknowledged_alerts_filter(client, alert_store) -> None:
    """?acknowledged=true should return only alerts an engineer has seen."""
    a = _unsafe_pump_alert("event-1")
    b = build_alert(
        "event-2",
        ReasonCode.TANK_ABOVE_HIGH_LIMIT,
        {"tank_level": 95.0, "high_level_limit": 90.0, "mode": "running"},
    )
    alert_store.upsert(a)
    alert_store.upsert(b)
    alert_store.acknowledge(a.alert_id)

    response = client.get("/api/alerts", params={"acknowledged": "true"})
    assert response.status_code == 200
    assert [item["alert_id"] for item in response.json()] == [a.alert_id]


def test_acknowledged_alias_routes_are_dropped(client) -> None:
    """The convenience alias sub-paths no longer exist as routes.

    ``/alerts/unacknowledged`` and ``/alerts/acknowledged`` duplicated
    ``?acknowledged=`` and were never called by the dashboard, so they were
    removed to leave one filtering route. They must be absent from the schema —
    not merely shadowed — so nothing depends on them.
    """
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/alerts/unacknowledged" not in paths
    assert "/api/alerts/acknowledged" not in paths


def test_alerts_query_param_selects_acknowledged(client, alert_store) -> None:
    """The list route's acknowledged=true query returns only acknowledged alerts."""
    a = _unsafe_pump_alert("event-1")
    alert_store.upsert(a)
    alert_store.acknowledge(a.alert_id)
    alert_store.upsert(_unsafe_pump_alert("event-2"))

    acked = client.get("/api/alerts", params={"acknowledged": "true"}).json()
    assert [item["alert_id"] for item in acked] == [a.alert_id]


def test_get_alert_by_id_returns_full_contract(client, alert_store) -> None:
    """Fetching one alert by id returns its full contract, for ID search/copy."""
    alert = _unsafe_pump_alert("event-1")
    alert_store.upsert(alert)

    response = client.get(f"/api/alerts/{alert.alert_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["alert_id"] == alert.alert_id
    assert payload["reason_code"] == "unsafe_pump_start"
    assert payload["title"]
    assert payload["explanation"]


def test_missing_alert_returns_404(client, alert_store) -> None:
    """A missing alert id should return a 404."""
    response = client.get("/api/alerts/not-found")
    assert response.status_code == 404
    assert response.json()["detail"] == "alert not found"


def test_acknowledge_alert_persists(client, alert_store) -> None:
    """Acknowledgement should persist in the store and survive a re-read."""
    alert = _unsafe_pump_alert("event-1")
    alert_store.upsert(alert)

    response = client.patch(f"/api/alerts/{alert.alert_id}/ack")
    assert response.status_code == 200
    payload = response.json()
    assert payload["alert_id"] == alert.alert_id
    assert payload["acknowledged"] is True
    assert alert_store.get(alert.alert_id)["acknowledged"] is True


def test_acknowledge_unknown_alert_returns_404(client, alert_store) -> None:
    """Acknowledging an unknown alert should 404, not report false success."""
    response = client.patch("/api/alerts/does-not-exist/ack")
    assert response.status_code == 404
