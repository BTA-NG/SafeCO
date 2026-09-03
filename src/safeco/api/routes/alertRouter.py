from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from safeco.api.deps import StoreDep

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
async def list_alerts(
    limit: int = Query(default=50, ge=1, le=500),
    acknowledged: bool | None = None,
    store: StoreDep = None,
) -> list[dict[str, Any]]:
    """Return the current alert feed.

    The event store is the source of persistent evidence; the alert layer is a
    read-only dashboard surface for now. This route intentionally returns an empty
    list until a dedicated alert persistence table is added.
    """
    _ = store, acknowledged, limit
    return []


@router.get("/alerts/unacknowledged")
async def list_unacknowledged_alerts(
    limit: int = Query(default=50, ge=1, le=500),
    store: StoreDep = None,
) -> list[dict[str, Any]]:
    """Return the pending alert queue."""
    _ = store, limit
    return []


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str, store: StoreDep = None) -> dict[str, Any]:
    """Return a specific alert by id.

    This is a contract placeholder until a dedicated alert store exists.
    """
    _ = store
    raise HTTPException(status_code=404, detail="alert not found")


@router.patch("/alerts/{alert_id}/ack")
async def acknowledge_alert(alert_id: str, store: StoreDep = None) -> dict[str, Any]:
    """Mark an alert as acknowledged.

    This endpoint is intentionally minimal until the project introduces a real
    alert persistence table.
    """
    _ = store
    return {"alert_id": alert_id, "acknowledged": True}

