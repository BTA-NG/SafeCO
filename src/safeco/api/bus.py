"""In-process change bus backing the live update stream.

The dashboard's stream needs to know the moment stored state changes. Watching
for that inside each stream would mean every connected console running its own
polling loop against SQLite -- the cost the stream exists to remove. Instead the
routes that mutate state announce it here, once, and every open stream wakes.

A notification says only *that* something changed, never what: a woken
subscriber re-reads the stores. That keeps the payload assembled in exactly one
place, keeps the stream's opening snapshot and later updates identical in shape,
and makes a notification idempotent, so a coalesced or repeated one can never
leave a console showing data that never existed.

Publishing is thread-safe. The scenario-run and acknowledgement handlers are
synchronous, so Starlette runs them in a threadpool rather than on the event
loop, and the bus is published to from those threads.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from contextlib import contextmanager


class ChangeBus:
    """Fan out "stored state changed" notifications to subscribed streams."""

    def __init__(self) -> None:
        """Create an empty bus with no subscribers."""
        self._subscribers: dict[asyncio.Queue[None], asyncio.AbstractEventLoop] = {}
        self._lock = threading.Lock()

    @contextmanager
    def subscribe(self) -> Iterator[asyncio.Queue[None]]:
        """Yield a queue that receives one item per change the subscriber owes.

        The queue holds at most one item. A subscriber that has not yet woken
        already has a change waiting, and a second would tell it nothing new
        while letting a slow one fall further behind.

        Must be entered from the event loop that will await the queue; the queue
        is woken from whichever thread publishes.

        Yields:
            A single-slot queue. An item on it means "re-read the stores".

        """
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscribers[queue] = loop
        try:
            yield queue
        finally:
            with self._lock:
                self._subscribers.pop(queue, None)

    def publish(self) -> None:
        """Notify every subscriber that stored state changed.

        Safe to call from any thread. Never blocks on a subscriber: a stream
        that is mid-render has its notification left waiting rather than
        stalling the route that published.
        """
        with self._lock:
            subscribers = list(self._subscribers.items())
        for queue, loop in subscribers:
            loop.call_soon_threadsafe(_offer, queue)

    def subscriber_count(self) -> int:
        """Return how many streams are currently subscribed.

        Returns:
            The number of live subscriptions.

        """
        with self._lock:
            return len(self._subscribers)


def _offer(queue: asyncio.Queue[None]) -> None:
    """Queue one change, ignoring the overflow when one is already pending."""
    try:
        queue.put_nowait(None)
    except asyncio.QueueFull:
        pass
