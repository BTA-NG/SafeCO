"""Dependencies shared by the SafeCO FastAPI routes."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import Depends

from safeco.storage import EventStore


def _is_open(store: EventStore | None) -> bool:
    """Return True if the store has a live (non-closed) connection.

    A closed sqlite3 connection raises ``ProgrammingError`` on use; that is the
    signal we reopen on, rather than swallowing every possible error.
    """
    if store is None:
        return False
    try:
        store.connection.execute("SELECT 1")
        return True
    except sqlite3.ProgrammingError:
        return False


def get_store() -> EventStore:
    """Return the shared SQLite event store for API request handlers.

    Reuses the store injected by the app lifespan (or a test). If none exists,
    or the existing one has been closed, a fresh store is opened against the
    configured database path so a handler never receives a dead connection.
    """
    from safeco.app import app, database_path

    store = getattr(app.state, "store", None)
    if not _is_open(store):
        store = EventStore(database_path())
        app.state.store = store
    return store


StoreDep = Annotated[EventStore, Depends(get_store)]
