"""Alert feed routes for the SafeCO API.

SCAFFOLD: these routes read and mutate an in-memory ``app.state.alerts`` list.
They are wiring for the dashboard alert view, not a completed feature. Alerts
are not produced by the detector here and are not persisted, so state is lost on
restart. Durable alert storage backed by the shared alert contract is deferred to
a future milestone. Do not treat alert retrieval or acknowledgement as complete.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
async def list_alerts(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    acknowledged: bool | None = None,
) -> list[dict[str, Any]]:
    """Return the current in-memory alert feed (scaffold, not persisted)."""
    alerts: list[dict[str, Any]] = getattr(request.app.state, "alerts", [])
    if acknowledged is not None:
        alerts = [
            alert for alert in alerts if alert.get("acknowledged") is acknowledged
        ]
    return sorted(alerts, key=lambda item: item.get("alert_id", ""))[:limit]


@router.get("/alerts/unacknowledged")
async def list_unacknowledged_alerts(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Return the pending alert queue (scaffold, not persisted)."""
    alerts: list[dict[str, Any]] = getattr(request.app.state, "alerts", [])
    results = [alert for alert in alerts if alert.get("acknowledged") is False]
    return sorted(results, key=lambda item: item.get("alert_id", ""))[:limit]


@router.get("/alerts/{alert_id}")
async def get_alert(request: Request, alert_id: str) -> dict[str, Any]:
    """Return a specific alert by id, or 404 if it is not in memory."""
    alerts: list[dict[str, Any]] = getattr(request.app.state, "alerts", [])
    for alert in alerts:
        if alert.get("alert_id") == alert_id:
            return alert
    raise HTTPException(status_code=404, detail="alert not found")


@router.patch("/alerts/{alert_id}/ack")
async def acknowledge_alert(request: Request, alert_id: str) -> dict[str, Any]:
    """Acknowledge an alert in the in-memory state (scaffold, not persisted).

    Validates that the alert exists (404 otherwise) and flips its acknowledged
    flag on the in-memory record. The acknowledgement is not durably stored and
    is lost on restart until persistent alert storage exists.
    """
    alerts: list[dict[str, Any]] = getattr(request.app.state, "alerts", [])
    for alert in alerts:
        if alert.get("alert_id") == alert_id:
            alert["acknowledged"] = True
            return {"alert_id": alert_id, "acknowledged": True}
    raise HTTPException(status_code=404, detail="alert not found")
