"""Regression guard for the TestClient/lifespan/shared-store hang.

A clean-environment run of the API test modules previously wedged at the health
route because the app opened the real ``data/safeco.db`` on first request and
blocked on its WAL lock. These tests drive the request path the API modules use
— through the running lifespan, in this process — and assert the endpoints answer
promptly, so the regression fails loudly instead of hanging the whole suite.

This is a guard, not the fix: the fix is that the lifespan opens a temporary
store (never ``data/safeco.db``) and closes it deterministically. The timing
assertion is generous and only catches a true stall, never normal latency.
"""

from __future__ import annotations

import time


def test_health_endpoint_returns_promptly(client) -> None:
    """The health route must answer quickly through the running lifespan."""
    start = time.perf_counter()
    response = client.get("/api/health")
    elapsed = time.perf_counter() - start
    assert response.status_code == 200
    # A healthy call is milliseconds; the previous hang exceeded 15s. Five
    # seconds cleanly separates "working" from "stalled" without being flaky.
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
