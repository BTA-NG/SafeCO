"""Tests for the SafeCO live update stream.

The dashboard used to re-fetch four endpoints on a two-second timer, so a new
finding could sit invisible for up to two seconds and every client paid for its
own polling. This module pins the replacement: one Server-Sent Events stream
that sends a full snapshot on connect and a fresh one whenever the stores
change, so the console renders the moment data lands.

The stream carries the same payload shape the dashboard already renders, so the
client's render path is unchanged — only the transport behind it is.

A stream never ends, which rules out the test client: ``TestClient`` buffers the
whole response body and runs the app to completion, so *requesting* an endless
stream hangs rather than returning. These tests drive the ASGI callable directly
and read frames as they are produced, which also lets a test make a real
mutating request while the stream is open.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from collections.abc import AsyncIterator
from typing import Any

from safeco.api.bus import ChangeBus
from safeco.api.routes import stream_router as stream_module
from safeco.app import app

STREAM_PATH = "/api/stream"

# Every read is bounded. An endless stream that stops producing frames should
# fail the test that is waiting on it, never wedge the suite.
READ_TIMEOUT = 5.0

# Distinguishes "this frame carried no payload" from a payload of JSON null.
_NO_DATA = object()


class _Stream:
    """One open ``/api/stream`` response, read frame by frame.

    Frames are collected from a queue the app writes into as it produces them,
    so a test observes the stream live rather than after it has closed.
    """

    def __init__(self) -> None:
        """Create a stream that has not received anything yet."""
        self.status_code: int | None = None
        self.headers: dict[str, str] = {}
        self._frames: asyncio.Queue[str] = asyncio.Queue()
        self._started = asyncio.Event()
        self._partial = ""

    async def send(self, message: dict[str, Any]) -> None:
        """Accept one ASGI message from the app under test."""
        if message["type"] == "http.response.start":
            self.status_code = message["status"]
            self.headers = {
                key.decode(): value.decode()
                for key, value in message.get("headers", [])
            }
            self._started.set()
        elif message["type"] == "http.response.body":
            self._partial += message.get("body", b"").decode()
            while "\n\n" in self._partial:
                frame, self._partial = self._partial.split("\n\n", 1)
                self._frames.put_nowait(frame)

    async def started(self, timeout: float = READ_TIMEOUT) -> None:
        """Wait until the response head has been sent."""
        await asyncio.wait_for(self._started.wait(), timeout)

    async def frame(self, timeout: float = READ_TIMEOUT) -> str:
        """Return the next frame exactly as it went out on the wire."""
        return await asyncio.wait_for(self._frames.get(), timeout)

    async def event(self, timeout: float = READ_TIMEOUT) -> tuple[str | None, Any]:
        """Return the next named event and its decoded payload.

        Comment frames (keep-alives) and the opening ``retry`` frame carry no
        data and are skipped, which is what a browser's ``EventSource`` does
        with them too.
        """
        while True:
            name: str | None = None
            payload: Any = _NO_DATA
            for line in (await self.frame(timeout)).split("\n"):
                if line.startswith("event:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    payload = json.loads(line.split(":", 1)[1].strip())
            if payload is not _NO_DATA:
                return name, payload


@contextlib.asynccontextmanager
async def _open_stream() -> AsyncIterator[_Stream]:
    """Open ``GET /api/stream`` straight through the ASGI app.

    Driving the callable directly is the only way to read a response that never
    completes (see the module docstring). Releasing the connection is what
    unsubscribes: the ``http.disconnect`` message sent on exit is the same one a
    real client's dropped socket produces, so the shutdown path under test is
    the one production takes.
    """
    stream = _Stream()
    disconnected = asyncio.Event()

    async def receive() -> dict[str, Any]:
        await disconnected.wait()
        return {"type": "http.disconnect"}

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": STREAM_PATH,
        "raw_path": STREAM_PATH.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
        "client": ("testserver", 50000),
        "server": ("testserver", 80),
        "state": {},
    }

    task = asyncio.create_task(app(scope, receive, stream.send))
    try:
        yield stream
    finally:
        disconnected.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(task, READ_TIMEOUT)
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await task


def test_stream_serves_event_stream(client) -> None:
    """The stream route answers with the SSE media type."""

    async def scenario() -> None:
        async with _open_stream() as stream:
            await stream.started()

            assert stream.status_code == 200
            assert stream.headers["content-type"].startswith("text/event-stream")
            # A stream is per-connection state, so no cache or proxy may hold it.
            assert stream.headers["cache-control"] == "no-cache"

    asyncio.run(scenario())


def test_stream_opens_with_a_full_snapshot(client) -> None:
    """Connecting yields one snapshot with everything the console renders.

    The client should not need a single follow-up request to paint its first
    screen, so the opening frame carries the same four payloads the polling
    client used to fetch separately.
    """

    async def scenario() -> None:
        async with _open_stream() as stream:
            event, payload = await stream.event()

        assert event == "snapshot"
        assert set(payload) == {"health", "plant", "events", "alerts"}
        assert payload["health"]["status"] in {"ok", "degraded"}
        assert payload["plant"]["status"] == "no_data"
        assert payload["events"] == []
        assert payload["alerts"] == []

    asyncio.run(scenario())


def test_stream_pushes_an_update_when_a_scenario_persists(client) -> None:
    """A scenario run lands on open streams without the client asking.

    This is the point of the stream: the run route announces the change, so the
    console does not wait out a poll interval to show it.
    """

    async def scenario() -> None:
        async with _open_stream() as stream:
            assert (await stream.event())[0] == "snapshot"

            run = await asyncio.to_thread(client.post, "/api/scenarios/startup_01/run")
            assert run.status_code == 200

            event, payload = await stream.event()

        assert event == "update"
        assert len(payload["events"]) > 0
        assert payload["plant"]["status"] == "ok"
        assert payload["health"]["event_count"] == len(payload["events"])

    asyncio.run(scenario())


def test_acknowledging_an_alert_pushes_an_update(client) -> None:
    """An acknowledgement reaches other viewers, so a queue never goes stale.

    The acknowledging engineer sees their own click resolve; every other open
    console needs the push to drop the alert out of the pending queue.
    """

    async def scenario() -> None:
        # The injection attack is the scenario that raises a finding to ack.
        run = await asyncio.to_thread(
            client.post, "/api/scenarios/attack_injection_01/run"
        )
        assert run.status_code == 200
        pending = await asyncio.to_thread(client.get, "/api/alerts?acknowledged=false")
        alert_id = pending.json()[0]["alert_id"]

        async with _open_stream() as stream:
            assert (await stream.event())[0] == "snapshot"

            ack = await asyncio.to_thread(client.patch, f"/api/alerts/{alert_id}/ack")
            assert ack.status_code == 200

            event, payload = await stream.event()

        assert event == "update"
        acknowledged = {a["alert_id"] for a in payload["alerts"] if a["acknowledged"]}
        assert alert_id in acknowledged

    asyncio.run(scenario())


def test_stream_keeps_the_connection_alive_when_idle(client, monkeypatch) -> None:
    """An idle stream emits comments so proxies do not drop a quiet connection.

    A raw TCP connection with no traffic for a minute looks dead to an
    intermediary, and a dropped stream reads to the console as a lost feed.
    """
    monkeypatch.setattr(stream_module, "POLL_SECONDS", 0.01)
    monkeypatch.setattr(stream_module, "KEEPALIVE_SECONDS", 0.05)

    async def scenario() -> None:
        async with _open_stream() as stream:
            for _ in range(10):
                if (await stream.frame(timeout=2.0)).startswith(": keepalive"):
                    return
            raise AssertionError("no keepalive comment on an idle stream")

    asyncio.run(scenario())


def test_stream_subscribes_to_the_shared_bus(client) -> None:
    """The stream listens on the bus the routes publish to.

    A stream subscribed to a bus of its own would sit silent while every unit
    test still passed, so this pins the wiring end to end — and that closing the
    connection releases the subscription, so a long-lived API cannot leak one
    per console that has come and gone.
    """

    async def scenario() -> None:
        async with _open_stream() as stream:
            assert (await stream.event())[0] == "snapshot"

            bus = app.state.bus
            assert isinstance(bus, ChangeBus)
            assert bus.subscriber_count() == 1

        assert bus.subscriber_count() == 0

    asyncio.run(scenario())


def test_bus_delivers_a_publish_to_every_subscriber() -> None:
    """One publish wakes every waiter, not just the first."""

    async def scenario() -> None:
        bus = ChangeBus()
        with bus.subscribe() as first, bus.subscribe() as second:
            bus.publish()
            await asyncio.wait_for(first.get(), timeout=1)
            await asyncio.wait_for(second.get(), timeout=1)

    asyncio.run(scenario())


def test_bus_publish_is_safe_from_another_thread() -> None:
    """Routes run in a threadpool, so publishing must cross threads.

    The scenario and ack handlers are synchronous, which Starlette runs off the
    event loop. A bus that only worked on the loop thread would drop every
    notification the API actually makes.
    """

    async def scenario() -> None:
        bus = ChangeBus()
        with bus.subscribe() as queue:
            thread = threading.Thread(target=bus.publish)
            thread.start()
            thread.join()
            await asyncio.wait_for(queue.get(), timeout=1)

    asyncio.run(scenario())


def test_bus_coalesces_a_backlog_into_one_notification() -> None:
    """A burst of changes leaves one pending wakeup, not a queue to drain.

    Subscribers re-read the stores when they wake, so a backlog of "something
    changed" says nothing more than a single one does — and it would let a slow
    client fall ever further behind.
    """

    async def scenario() -> None:
        bus = ChangeBus()
        with bus.subscribe() as queue:
            for _ in range(25):
                bus.publish()
            await asyncio.wait_for(queue.get(), timeout=1)
            assert queue.empty()

    asyncio.run(scenario())


def test_bus_forgets_a_subscriber_that_disconnects() -> None:
    """A closed stream stops receiving, so a long-lived API does not leak it."""

    async def scenario() -> None:
        bus = ChangeBus()
        with bus.subscribe():
            assert bus.subscriber_count() == 1
        assert bus.subscriber_count() == 0

    asyncio.run(scenario())
