"""Shared test fixtures for the SafeCO API.

API tests drive the app through ``TestClient`` used as a context manager, so the
real FastAPI lifespan runs: it creates the event and alert stores on startup and
closes them on shutdown. Both store paths are pinned to temporary databases via
``SAFECO_DATABASE`` / ``SAFECO_ALERT_DATABASE``, so the lifespan never opens the
production files and no test can wedge the suite on their locks. App state is
reset after each test, so nothing leaks between tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from safeco.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Yield a context-managed TestClient backed by temporary databases.

    Pins the event and alert database paths to temp files and clears any injected
    stores so the lifespan owns creation/teardown. Entering the ``with`` block
    runs startup (opening the temp stores); leaving it runs shutdown (closing
    them). App state is reset afterwards so the next test starts clean.
    """
    monkeypatch.setenv("SAFECO_DATABASE", str(tmp_path / "safeco_test.db"))
    monkeypatch.setenv("SAFECO_ALERT_DATABASE", str(tmp_path / "safeco_alerts_test.db"))
    app.state.store = None
    app.state.alert_store = None
    with TestClient(app) as test_client:
        yield test_client
    app.state.store = None
    app.state.alert_store = None


@pytest.fixture()
def event_store(client):
    """Return the event store the running lifespan created for this client."""
    return app.state.store


@pytest.fixture()
def alert_store(client):
    """Return the alert store the running lifespan created for this client."""
    return app.state.alert_store
