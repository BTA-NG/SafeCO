"""Health endpoint for the SafeCO API.

Reports whether the local collection feed is healthy or degraded so the
dashboard can surface degraded visibility instead of implying a healthy
system when no events are present.
"""

from __future__ import annotations

from fastapi import APIRouter

from safeco.api.deps import StoreDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_status(store: StoreDep) -> dict[str, object]:
    """Report the current local SafeCO status.

    The dashboard uses this endpoint to decide whether the local collection feed
    is healthy or degraded. If no events are present, the API exposes that state
    explicitly instead of silently reporting a healthy system.
    """
    latest = store.list_events(limit=1)
    if not latest:
        return {
            "status": "degraded",
            "database": "available",
            "last_event_timestamp": None,
            "degraded_visibility": True,
            "event_count": 0,
        }

    row = latest[0]
    return {
        "status": "ok",
        "database": "available",
        "last_event_timestamp": row["timestamp"],
        "degraded_visibility": False,
        "event_count": 1,
    }
