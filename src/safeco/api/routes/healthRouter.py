from __future__ import annotations

from safeco.api.deps import StoreDep
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_status(store: StoreDep) -> dict[str, object]:
    """Return the current health of the local SafeCO service.

    The current implementation is intentionally lightweight. It confirms that the
    SQLite store is reachable and reports the timestamp of the newest persisted
    event when available.
    """
    latest = store.list_events(limit=1)
    last_event_timestamp = latest[0]["timestamp"] if latest else None
    return {
        "status": "ok",
        "database": "available",
        "last_event_timestamp": last_event_timestamp,
        "degraded_visibility": False,
    }



