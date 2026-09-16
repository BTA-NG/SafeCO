"""Event feed routes for the SafeCO API.

Routes handle event retrieval, filtering, and polling with proper Event
contract deserialization.
"""

from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, HTTPException, Query

from safeco.api.deps import StoreDep
from safeco.events import Event, ProcessSnapshot

router = APIRouter(tags=["events"])


def _row_to_event(row: sqlite3.Row) -> Event:
    """Convert a SQLite row to an Event object.

    SQLite stores JSON fields as strings; this reconstructs the Event contract
    with properly parsed value and process fields.

    Args:
        row: A sqlite3.Row from the events table.

    Returns:
        An Event object with all fields properly deserialized.

    """
    # Deserialize the process JSON and reconstruct ProcessSnapshot
    process_dict = json.loads(row["process_json"])
    process = ProcessSnapshot(**process_dict)

    # Deserialize the value field
    value = json.loads(row["value_json"])

    # Deserialize the raw field
    raw = json.loads(row["raw_json"]) if row["raw_json"] else {}

    return Event(
        event_id=row["event_id"],
        timestamp=row["timestamp"],
        scenario_id=row["scenario_id"],
        ground_truth=row["ground_truth"],
        source=row["source"],
        command=row["command"],
        target=row["target"],
        value=value,
        mode=row["mode"],
        process=process,
        sequence_id=row["sequence_id"],
        raw=raw,
    )


@router.get("/events")
def list_events(
    limit: int = Query(default=50, ge=1, le=500),
    scenario_id: str | None = None,
    store: StoreDep = None,
) -> list[dict[str, object]]:
    """Return the most recent persisted events, newest first.

    Backs the dashboard's event feed. Each row is rebuilt into the Event
    contract shape (value and process deserialized from their stored JSON) so
    the client receives objects, not raw JSON strings.

    Args:
        limit: Maximum number of events to return (1-500).
        scenario_id: If given, restrict the feed to one scenario's events.
        store: The shared event store, injected per request.

    Returns:
        A list of event dicts in Event-contract shape, newest first.

    """
    rows = store.list_events(limit=limit, scenario_id=scenario_id)
    events = [_row_to_event(row) for row in rows]
    return [event.to_dict() for event in events]


@router.get("/events/{event_id}")
def get_event(event_id: str, store: StoreDep = None) -> dict[str, object]:
    """Return a single event by its UUID-style identifier.

    Args:
        event_id: The event's unique identifier.
        store: The shared event store, injected per request.

    Returns:
        The event dict with all contract fields, value and process deserialized.

    Raises:
        HTTPException: 404 if no event with that id is stored.

    """
    row = store.get_event(event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="event not found")
    event = _row_to_event(row)
    return event.to_dict()


@router.get("/events/after/{event_id}")
def get_events_after(
    event_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    store: StoreDep = None,
) -> list[dict[str, object]]:
    """Return the events recorded after a known event id, oldest first.

    Lets a client poll for new events since a checkpoint it already holds,
    instead of refetching the whole feed. Events come back in chronological
    order in full Event-contract shape.

    Args:
        event_id: The checkpoint event; only later events are returned.
        limit: Maximum number of events to return (1-500).
        store: The shared event store, injected per request.

    Returns:
        A list of event dicts recorded after the checkpoint, oldest first.

    Raises:
        HTTPException: 404 if the checkpoint event id is unknown.

    """
    try:
        rows = store.events_after(event_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    events = [_row_to_event(row) for row in rows]
    return [event.to_dict() for event in events]
