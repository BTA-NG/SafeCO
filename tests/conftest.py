"""Shared test fixtures for the SafeCO API.

API tests drive the app through ``TestClient`` used as a context manager, so the
real FastAPI lifespan runs: it creates the event store on startup and closes it
on shutdown. The store path is pinned to a temporary database via
``SAFECO_DATABASE``, so the lifespan never opens the production ``data/safeco.db``
and no test can wedge the suite on that file's lock. All app state is reset after
each test, so nothing leaks between tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from safeco.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Yield a context-managed TestClient backed by a temporary database.

    Pins ``SAFECO_DATABASE`` to a temp file and clears any injected store so the
    lifespan owns creation/teardown. Entering the ``with`` block runs startup
    (opening the temp store); leaving it runs shutdown (closing it). App state is
    reset afterwards so the next test starts clean.
    """
    monkeypatch.setenv("SAFECO_DATABASE", str(tmp_path / "safeco_test.db"))
    app.state.store = None
    app.state.alerts = []
    with TestClient(app) as test_client:
        yield test_client
    app.state.store = None
    app.state.alerts = []


@pytest.fixture()
def event_store(client):
    """Return the event store the running lifespan created for this client."""
    return app.state.store
