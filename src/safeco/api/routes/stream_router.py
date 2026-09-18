"""Server-Sent Events stream feeding the SafeCO dashboard.

The console used to re-fetch four endpoints on a two-second timer: a new
finding could sit invisible for up to two seconds, and every open console paid
for its own polling. This route replaces that with one long-lived response that
pushes a fresh payload the moment stored state changes.

Frames follow the SSE wire format:

* ``retry:`` once, so a browser reconnects on a sane interval;
* ``event: snapshot`` on connect, carrying everything the console renders, so
  the first screen needs no follow-up request;
* ``event: update`` whenever the stores change, carrying the same payload shape;
* ``: keepalive`` comments when nothing is happening, so an intermediary does
  not drop a quiet connection and present as a lost feed.

The payload is composed by calling the existing REST handlers rather than
re-deriving it, so the stream and the endpoints can never drift into two
versions of the same truth. Those handlers read SQLite synchronously, so every
call is dispatched to a thread: this generator runs on the event loop, and
blocking it would stall every other request the way the health route once did.

The stream reports what the server can see. A stream that drops is the client's
signal that SafeCO itself is unreachable, which no server-side payload can
report on its own behalf.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from safeco.alert_store import AlertStore
from safeco.api.bus import ChangeBus
from safeco.api.deps import AlertStoreDep, BusDep, StoreDep
from safeco.api.routes.alert_router import list_alerts
from safeco.api.routes.event_router import list_events
from safeco.api.routes.health_router import health_status
from safeco.api.routes.plant_state_router import plant_state
from safeco.storage import EventStore

router = APIRouter(tags=["stream"])

# Match the window the dashboard asks the REST endpoints for, so switching the
# console onto the stream does not change how much history it can page through.
STREAM_LIMIT = 500

# How often an otherwise idle stream re-checks the stores. Changes made through
# this process arrive instantly on the bus; this is the safety net for writes
# from outside it, such as a collection feed running as its own process.
POLL_SECONDS = 2.0

# How long a stream may stay silent before it emits a comment.
KEEPALIVE_SECONDS = 15.0


def _frame(event: str, payload: dict[str, object]) -> str:
    """Render one named SSE frame carrying a JSON payload."""
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _snapshot(store: EventStore, alert_store: AlertStore) -> dict[str, object]:
    """Assemble the payload the dashboard renders.

    Composed from the existing route handlers rather than re-derived, so the
    stream and the REST endpoints cannot disagree about what the console shows.

    Args:
        store: The shared event store.
        alert_store: The shared alert store.

    Returns:
        A dict with the ``health``, ``plant``, ``events``, and ``alerts``
        payloads, each identical to what its REST endpoint returns.

    """
    return {
        "health": health_status(store),
        "plant": plant_state(store),
        "events": list_events(limit=STREAM_LIMIT, store=store),
        "alerts": list_alerts(alert_store, limit=STREAM_LIMIT),
    }


def _fingerprint(store: EventStore, alert_store: AlertStore) -> tuple[object, ...]:
    """Return a cheap value that changes whenever the console's view would.

    In-process changes wake a stream directly, so this only has to catch writes
    from outside the process. Counts and the newest id are enough for that, and
    far cheaper than building a payload to compare.

    Args:
        store: The shared event store.
        alert_store: The shared alert store.

    Returns:
        A tuple that differs from the previous call's whenever new events have
        been recorded or an alert has been added or acknowledged.

    """
    latest = store.list_events(limit=1)
    return (
        store.count_events(),
        latest[0]["event_id"] if latest else None,
        len(alert_store.list_alerts(limit=STREAM_LIMIT)),
        len(alert_store.list_alerts(acknowledged=True, limit=STREAM_LIMIT)),
    )


async def _stream(
    bus: ChangeBus, store: EventStore, alert_store: AlertStore
) -> AsyncIterator[str]:
    """Yield SSE frames until the client goes away.

    Args:
        bus: The change bus the mutating routes publish on.
        store: The shared event store.
        alert_store: The shared alert store.

    Yields:
        SSE frames: the opening snapshot, then an update per change, with
        keepalive comments while idle.

    """
    with bus.subscribe() as changes:
        seen = await asyncio.to_thread(_fingerprint, store, alert_store)
        yield "retry: 3000\n\n"
        yield _frame("snapshot", await asyncio.to_thread(_snapshot, store, alert_store))

        idle = 0.0
        while True:
            try:
                await asyncio.wait_for(changes.get(), timeout=POLL_SECONDS)
            except TimeoutError:
                idle += POLL_SECONDS
            else:
                idle = 0.0

            current = await asyncio.to_thread(_fingerprint, store, alert_store)
            if current != seen:
                seen = current
                idle = 0.0
                payload = await asyncio.to_thread(_snapshot, store, alert_store)
                yield _frame("update", payload)
            elif idle >= KEEPALIVE_SECONDS:
                idle = 0.0
                yield ": keepalive\n\n"


@router.get("/stream")
async def stream(
    bus: BusDep, store: StoreDep, alert_store: AlertStoreDep
) -> StreamingResponse:
    """Stream live console updates to one dashboard, pushed rather than polled.

    Opens with a snapshot so the console paints its first screen from a single
    request, then sends a fresh payload whenever events are recorded or alerts
    change. The connection stays open for the life of the page; closing it is
    how a client unsubscribes.

    Args:
        bus: The process-wide change bus the mutating routes publish on.
        store: The shared event store, injected per request.
        alert_store: The shared alert store, injected per request.

    Returns:
        A ``text/event-stream`` response that stays open until the client
        disconnects.

    """
    return StreamingResponse(
        _stream(bus, store, alert_store),
        media_type="text/event-stream",
        headers={
            # A stream is per-connection state; no cache or proxy may hold it.
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Tell a reverse proxy not to buffer, which would defeat the push.
            "X-Accel-Buffering": "no",
        },
    )
