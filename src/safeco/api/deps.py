"""Dependencies shared by the SafeCO FastAPI routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from safeco.storage import EventStore


def get_store() -> EventStore:
    """Return the shared SQLite event store for API request handlers.

    The app creates a single store at startup and reuses it across requests.
    """
    from safeco.app import app

    store = getattr(app.state, "store", None)
    if store is None:
        store = EventStore("data/safeco.db")
        app.state.store = store
    return store


StoreDep = Annotated[EventStore, Depends(get_store)]
