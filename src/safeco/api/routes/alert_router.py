"""Alert feed routes for the SafeCO API.

These routes serve detector alerts from the persistent ``AlertStore`` and record
engineer acknowledgement. Alerts are produced by the detector (for example when
a scenario is run) and keyed by a deterministic id, so acknowledgement survives
restarts and detector replay. The API only reads and acknowledges alerts; it
never issues or blocks a control action, and acknowledgement is an engineer
record, not an action SafeCO takes on the plant.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from safeco.api.deps import AlertStoreDep

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
def list_alerts(
    store: AlertStoreDep,
    limit: int = Query(default=50, ge=1, le=500),
    acknowledged: bool | None = None,
) -> list[dict[str, object]]:
    """Return persisted alerts, most urgent first, optionally filtered by ack."""
    return store.list_alerts(acknowledged=acknowledged, limit=limit)


@router.get("/alerts/unacknowledged")
def list_unacknowledged_alerts(
    store: AlertStoreDep,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, object]]:
    """Return the pending (unacknowledged) alert queue."""
    return store.list_alerts(acknowledged=False, limit=limit)


@router.get("/alerts/{alert_id}")
def get_alert(store: AlertStoreDep, alert_id: str) -> dict[str, object]:
    """Return a specific alert by id, or 404 if it is not stored."""
    alert = store.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return alert


@router.patch("/alerts/{alert_id}/ack")
def acknowledge_alert(store: AlertStoreDep, alert_id: str) -> dict[str, object]:
    """Record an engineer's acknowledgement of an alert.

    Validates that the alert exists (404 otherwise) and persists the
    acknowledgement. This marks that a human has seen the advisory finding; it
    does not change the plant.
    """
    if not store.acknowledge(alert_id):
        raise HTTPException(status_code=404, detail="alert not found")
    return {"alert_id": alert_id, "acknowledged": True}
