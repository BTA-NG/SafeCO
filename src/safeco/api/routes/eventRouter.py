from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from safeco.api.deps import StoreDep

router = APIRouter(tags=["events"])


@router.get("/events")
async def list_events(
    limit: int = Query(default=50, ge=1, le=500),
    scenario_id: str | None = None,
    store: StoreDep = None,
) -> list[dict[str, object]]:
    """Return the most recent persisted events.

    The dashboard uses this feed to render the event stream and can optionally
    filter by scenario.
    """
    rows = store.list_events(limit=limit, scenario_id=scenario_id)
    return [dict(row) for row in rows]


@router.get("/events/{event_id}")
async def get_event(event_id: str, store: StoreDep = None) -> dict[str, object]:
    """Return a single event by its UUID-style identifier."""
    row = store.connection.execute(
        "SELECT * FROM events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="event not found")
    return dict(row)


@router.get("/events/after/{event_id}")
async def get_events_after(
    event_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    store: StoreDep = None,
) -> list[dict[str, object]]:
    """Return the persisted events that occurred after a known event id."""
    try:
        rows = store.events_after(event_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [dict(row) for row in rows]

