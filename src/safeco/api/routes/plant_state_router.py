"""Plant state endpoint for the SafeCO API.

Returns the latest process snapshot from the event stream with full Event
contract shape for consistent data model across all routes.
"""

from __future__ import annotations

from fastapi import APIRouter

from safeco.api.deps import StoreDep
from safeco.api.routes.event_router import _row_to_event

router = APIRouter(tags=["plant"])


@router.get("/plant/state")
def plant_state(store: StoreDep) -> dict[str, object]:
    """Return the latest plant process snapshot for the dashboard.

    The newest persisted event carries the current process state, so this reads
    the most recent event and returns it in full Event-contract shape with a
    ``status`` field added. When the store is empty it returns an explicit
    ``no_data`` status with a null process, rather than a bare null, so the
    dashboard can distinguish "no data yet" from "data present".

    Args:
        store: The shared event store, injected per request.

    Returns:
        On data: the newest event dict plus ``status="ok"``. When empty:
        ``{"status": "no_data", "process": None}``.

    """
    latest = store.list_events(limit=1)
    if not latest:
        return {
            "status": "no_data",
            "process": None,
        }
    row = latest[0]
    event = _row_to_event(row)
    event_dict = event.to_dict()
    event_dict["status"] = "ok"
    return event_dict
