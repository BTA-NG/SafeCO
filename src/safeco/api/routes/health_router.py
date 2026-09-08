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
def health_status(store: StoreDep) -> dict[str, object]:
    """Report the health of the local collection feed for the dashboard.

    SafeCO can only detect what it observes, so the dashboard must be able to
    tell the operator when visibility is degraded rather than implying all is
    well. When no events have been collected this returns a ``degraded`` status
    with ``degraded_visibility`` true; otherwise it reports the newest event
    timestamp and the total number of stored events.

    Args:
        store: The shared event store, injected per request.

    Returns:
        A status dict with ``status`` (``ok``/``degraded``), ``database``
        availability, ``last_event_timestamp``, a ``degraded_visibility`` flag,
        and the total ``event_count``.

    """
    count = store.count_events()
    if count == 0:
        return {
            "status": "degraded",
            "database": "available",
            "last_event_timestamp": None,
            "degraded_visibility": True,
            "event_count": 0,
        }

    latest = store.list_events(limit=1)
    return {
        "status": "ok",
        "database": "available",
        "last_event_timestamp": latest[0]["timestamp"],
        "degraded_visibility": False,
        "event_count": count,
    }
