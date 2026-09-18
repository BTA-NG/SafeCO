"""Alert feed routes for the SafeCO API.

These routes serve detector alerts from the persistent ``AlertStore`` and record
engineer acknowledgement. Alerts are produced by the detector (for example when
a scenario is run) and keyed by a deterministic id, so acknowledgement survives
restarts and detector replay. The API only reads and acknowledges alerts; it
never issues or blocks a control action, and acknowledgement is an engineer
record, not an action SafeCO takes on the plant.

Acknowledged/unacknowledged views are served by ``GET /alerts?acknowledged=``
rather than dedicated sub-paths, so there is one filtering route to reason about.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from safeco.api.deps import AlertStoreDep, BusDep

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
def list_alerts(
    store: AlertStoreDep,
    limit: int = Query(default=50, ge=1, le=500),
    acknowledged: bool | None = None,
) -> list[dict[str, object]]:
    """Return persisted detector alerts for the dashboard queue.

    Alerts are ordered most-urgent-first (by severity, then id) so the operator
    sees the highest-severity findings at the top. The optional ``acknowledged``
    filter lets a caller request one side of the queue without client-side
    filtering: ``?acknowledged=false`` is the pending work list and
    ``?acknowledged=true`` the handled history.

    Args:
        store: The shared alert store, injected per request.
        limit: Maximum number of alerts to return (1-500).
        acknowledged: If ``True`` return only acknowledged alerts, if ``False``
            only unacknowledged; if omitted (``None``) return both.

    Returns:
        A list of alert dicts in the shared alert-contract shape.

    """
    return store.list_alerts(acknowledged=acknowledged, limit=limit)


@router.get("/alerts/{alert_id}")
def get_alert(store: AlertStoreDep, alert_id: str) -> dict[str, object]:
    """Return one alert by its deterministic id.

    Backs the dashboard's "search by alert id" flow: an operator can copy an id
    from the queue and look the finding up directly.

    Args:
        store: The shared alert store, injected per request.
        alert_id: The deterministic UUID5 identifier of the alert.

    Returns:
        The alert dict in the shared alert-contract shape.

    Raises:
        HTTPException: 404 if no alert with that id is stored.

    """
    alert = store.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return alert


@router.patch("/alerts/{alert_id}/ack")
def acknowledge_alert(
    store: AlertStoreDep, bus: BusDep, alert_id: str
) -> dict[str, object]:
    """Record an engineer's acknowledgement of an alert.

    Validates that the alert exists and persists the acknowledgement so it
    survives restarts and detector replay. This marks that a human has seen the
    advisory finding; it never changes the plant.

    The acknowledgement announces itself on the change bus, so one engineer's
    click drops the alert out of every other open console's pending queue rather
    than leaving their views disagreeing about what is still outstanding.

    Args:
        store: The shared alert store, injected per request.
        bus: The change bus the live stream listens on.
        alert_id: The deterministic identifier of the alert to acknowledge.

    Returns:
        A small confirmation dict echoing the id and the acknowledged flag.

    Raises:
        HTTPException: 404 if no alert with that id is stored, so the API never
            reports success for an alert that was never recorded.

    """
    if not store.acknowledge(alert_id):
        raise HTTPException(status_code=404, detail="alert not found")
    bus.publish()
    return {"alert_id": alert_id, "acknowledged": True}
