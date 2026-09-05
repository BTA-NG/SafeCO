"""Shared test fixtures for the SafeCO API.

Every API test runs against a temporary ``EventStore`` injected through
FastAPI's dependency override, never the real ``data/safeco.db``. The store is
closed and all app state is cleared after each test, so no connection leaks
between tests and no test can wedge the suite on a locked production database.
"""

from __future__ import annotations

import pytest

from safeco.api.deps import get_store
from safeco.app import app
from safeco.storage import EventStore


@pytest.fixture(autouse=True)
def api_store(tmp_path, monkeypatch):
    """Inject a per-test temporary event store and clean it up afterwards.

    Yields the store so a test can seed events directly. The same instance is
    returned by the ``get_store`` dependency and exposed on ``app.state.store``
    for the code paths that read state without the dependency.
    """
    # Belt and braces: even if some path bypasses the override and reads the
    # configured path, point it away from data/safeco.db.
    monkeypatch.setenv("SAFECO_DATABASE", str(tmp_path / "safeco_test.db"))

    store = EventStore(tmp_path / "api_test.db")
    app.state.store = store
    app.state.alerts = []
    app.dependency_overrides[get_store] = lambda: store
    try:
        yield store
    finally:
        app.dependency_overrides.pop(get_store, None)
        store.close()
        app.state.store = None
        app.state.alerts = []
