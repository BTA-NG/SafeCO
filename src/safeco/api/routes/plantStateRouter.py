from __future__ import annotations

import json

from fastapi import APIRouter

from safeco.api.deps import StoreDep

router = APIRouter(tags=["plant"])


@router.get("/plant/state")
async def plant_state(store: StoreDep) -> dict[str, object]:
    """Return the latest process snapshot from the persisted event stream.

    The response keeps the same event metadata as the underlying store, while
    also exposing an explicit status field for the dashboard. This makes it clear
    when the system is showing live data versus no-data state.
    """
    latest = store.list_events(limit=1)
    if not latest:
        return {
            "status": "no_data",
            "process": None,
        }
    row = latest[0]
    payload = json.loads(row["process_json"])
    return {
        "status": "ok",
        "event_id": row["event_id"],
        "timestamp": row["timestamp"],
        "scenario_id": row["scenario_id"],
        "process": payload,
    }

