"""Regression guard for the TestClient/lifespan/shared-store hang.

The reported symptom: in a clean checkout the suite stalls at the health route,
and even a minimal ``TestClient(app).get("/api/health")`` never returns — even
with a temporary ``EventStore`` injected, so it is not the production database.

Root cause: the DB-backed routes were ``async def`` but made blocking SQLite
calls, so the work ran on the event loop. Under TestClient's single-threaded
portal loop that parks the only thread available to deliver the response, which
presents as a hang on some event-loop/OS combinations. The fix makes those
handlers synchronous so Starlette runs them in its threadpool, keeping the loop
free. These tests drive both the reviewer's exact minimal repro and the
context-managed path, and assert prompt completion without touching
``data/safeco.db``.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from safeco.app import app
from safeco.storage import EventStore


def test_bare_testclient_health_returns_promptly(tmp_path, monkeypatch) -> None:
    """Mirror the reviewer's minimal repro: bare client, injected temp store.

    No context manager, an injected temporary EventStore, and SAFECO_DATABASE
    pointed away from data/safeco.db. The request must return quickly.
    """
    monkeypatch.setenv("SAFECO_DATABASE", str(tmp_path / "unused.db"))
    store = EventStore(tmp_path / "injected.db")
    app.state.store = store
    app.state.alerts = []
    try:
        start = time.perf_counter()
        response = TestClient(app).get("/api/health")
        elapsed = time.perf_counter() - start
        assert response.status_code == 200
        assert elapsed < 5.0, f"health took {elapsed:.2f}s — possible hang"
    finally:
        store.close()
        app.state.store = None


def test_health_endpoint_returns_promptly(client) -> None:
    """The health route must answer quickly through the running lifespan."""
    start = time.perf_counter()
    response = client.get("/api/health")
    elapsed = time.perf_counter() - start
    assert response.status_code == 200
    assert elapsed < 5.0, f"health endpoint took {elapsed:.2f}s — possible hang"


def test_repeated_requests_reuse_a_live_store(client) -> None:
    """Many sequential requests must all succeed on the shared connection.

    Exercises get_store returning a live (never closed) connection across
    repeated calls, the way the API test modules hit it in one process.
    """
    for _ in range(25):
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/events").status_code == 200
        assert client.get("/api/plant/state").status_code == 200
