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
    """Return the latest process snapshot from the persisted event stream.

    The response includes the full Event contract shape, including all event
    metadata (event_id, timestamp, scenario_id, etc.) and the process snapshot.
    If no events exist, returns a clear no-data status instead of null process.
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
