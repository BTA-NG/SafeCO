"""Dependencies shared by the SafeCO FastAPI routes."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import Depends

from safeco.alert_store import AlertStore
from safeco.api.bus import ChangeBus
from safeco.storage import EventStore


def _is_open(store: EventStore | AlertStore | None) -> bool:
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


def get_alert_store() -> AlertStore:
    """Return the shared persistent alert store for API request handlers.

    Mirrors ``get_store``: reuses the injected store and reopens against the
    configured alert-database path if none exists or it has been closed, so a
    handler never receives a dead connection.
    """
    from safeco.app import alert_database_path, app

    store = getattr(app.state, "alert_store", None)
    if not _is_open(store):
        store = AlertStore(alert_database_path())
        app.state.alert_store = store
    return store


def get_bus() -> ChangeBus:
    """Return the process-wide change bus for API request handlers.

    Routes that mutate stored state publish on this bus so the live update
    stream can push a fresh payload without polling. It is created on first use
    and kept on ``app.state``, so a route always publishes on the same bus that
    every open stream is listening to. The bus holds no resources to release,
    so it needs no lifespan teardown.

    Returns:
        The shared ``ChangeBus`` for this process.

    """
    from safeco.app import app

    bus = getattr(app.state, "bus", None)
    if bus is None:
        bus = ChangeBus()
        app.state.bus = bus
    return bus


StoreDep = Annotated[EventStore, Depends(get_store)]
AlertStoreDep = Annotated[AlertStore, Depends(get_alert_store)]
BusDep = Annotated[ChangeBus, Depends(get_bus)]
