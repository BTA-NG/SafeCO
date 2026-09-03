from __future__ import annotations

import json

from fastapi import APIRouter

from safeco.api.deps import StoreDep

router = APIRouter(tags=["plant"])


@router.get("/plant/state")
async def plant_state(store: StoreDep) -> dict[str, object]:
    """Return the latest plant snapshot from the persisted event stream."""
    latest = store.list_events(limit=1)
    if not latest:
        return {
            "status": "no_data",
            "process": None,
        }
    row = latest[0]
    payload = json.loads(row["process_json"])
    return {
        "event_id": row["event_id"],
        "timestamp": row["timestamp"],
        "scenario_id": row["scenario_id"],
        "process": payload,
    }

