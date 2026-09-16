"""Health endpoint for the SafeCO API.

Reports whether the local collection feed is healthy or degraded so the
dashboard can surface degraded visibility instead of implying a healthy
system when the feed has stopped delivering events.

Visibility degrades in two ways, and both must trip the flag:

* no event has ever been collected (the feed has not started); and
* events exist but the newest one has aged past the freshness window, meaning
  the feed has gone silent even though history is present.

The second case is the important one: a feed that dies after delivering events
leaves stale history behind, and keying the flag off ``event_count`` alone
would keep reporting a healthy system indefinitely. Comparing the newest event
against a freshness window lets a dead-but-previously-live feed trip the flag.

This is the server-side signal for "SafeCO is up but no longer seeing the
plant." It is distinct from, and complementary to, the client's own detection
of an unreachable API (a failed poll) — that condition means the dashboard
cannot reach SafeCO at all, which the server cannot report on its own behalf.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from safeco.api.deps import StoreDep

router = APIRouter(tags=["health"])

# How long the newest event may age before visibility is considered degraded.
# A live plant feed streams continuously, so a gap this long means SafeCO has
# lost its live view rather than simply being idle between commands.
STALE_AFTER_SECONDS = 120.0


def _feed_is_stale(last_timestamp: str, now: datetime) -> bool:
    """Return whether the newest event is too old to count as live visibility.

    Args:
        last_timestamp: ISO-8601 timestamp of the newest stored event.
        now: The current time, in UTC.

    Returns:
        ``True`` if the event is older than ``STALE_AFTER_SECONDS`` or its
        timestamp cannot be parsed. An unparseable timestamp is treated as
        stale so a malformed feed degrades safely rather than reporting health.

    """
    try:
        parsed = datetime.fromisoformat(last_timestamp)
    except (TypeError, ValueError):
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (now - parsed).total_seconds() > STALE_AFTER_SECONDS


@router.get("/health")
def health_status(store: StoreDep) -> dict[str, object]:
    """Report the health of the local collection feed for the dashboard.

    SafeCO can only detect what it observes, so the dashboard must be able to
    tell the operator when visibility is degraded rather than implying all is
    well. Visibility is degraded when no events have been collected yet, or
    when the newest event has aged past ``STALE_AFTER_SECONDS`` (the feed has
    gone silent). Otherwise it reports the newest event timestamp and the total
    number of stored events.

    Args:
        store: The shared event store, injected per request.

    Returns:
        A status dict with ``status`` (``ok``/``degraded``), ``database``
        availability, ``last_event_timestamp``, a ``degraded_visibility`` flag,
        and the total ``event_count``.

    """
    count = store.count_events()
    now = datetime.now(timezone.utc)

    if count == 0:
        last_timestamp = None
        degraded = True
    else:
        last_timestamp = store.list_events(limit=1)[0]["timestamp"]
        degraded = _feed_is_stale(last_timestamp, now)

    return {
        "status": "degraded" if degraded else "ok",
        "database": "available",
        "last_event_timestamp": last_timestamp,
        "degraded_visibility": degraded,
        "event_count": count,
    }
