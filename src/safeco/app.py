"""SafeCO FastAPI application."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from safeco.alert_store import AlertStore
from safeco.api.routes.alert_router import router as alert_router
from safeco.api.routes.event_router import router as event_router
from safeco.api.routes.health_router import router as health_router
from safeco.api.routes.plant_state_router import router as plant_state_router
from safeco.api.routes.scenario_router import router as scenario_router
from safeco.storage import EventStore

DEFAULT_DATABASE = "data/safeco.db"
DEFAULT_ALERT_DATABASE = "data/safeco_alerts.db"


def database_path() -> str:
    """Return the event-store path, overridable via ``SAFECO_DATABASE``.

    Production defaults to ``data/safeco.db``. Tests set the environment
    variable (or inject a store directly) so they never touch that file.
    """
    return os.environ.get("SAFECO_DATABASE", DEFAULT_DATABASE)


def alert_database_path() -> str:
    """Return the alert-store path, overridable via ``SAFECO_ALERT_DATABASE``.

    Production defaults to ``data/safeco_alerts.db`` — a separate file from the
    event store so the two never hold competing writer connections.
    """
    return os.environ.get("SAFECO_ALERT_DATABASE", DEFAULT_ALERT_DATABASE)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create and tear down shared resources deterministically.

    The lifespan only creates and closes what it owns. If a store has already
    been injected onto ``app.state`` (as tests do), it is left untouched so the
    injector controls its lifecycle and the real databases are never opened.
    """
    owns_store = getattr(app.state, "store", None) is None
    if owns_store:
        app.state.store = EventStore(database_path())
    owns_alert_store = getattr(app.state, "alert_store", None) is None
    if owns_alert_store:
        app.state.alert_store = AlertStore(alert_database_path())
    try:
        yield
    finally:
        if owns_store:
            app.state.store.close()
            app.state.store = None
        if owns_alert_store:
            app.state.alert_store.close()
            app.state.alert_store = None


app = FastAPI(
    title="SafeCO",
    version="0.1.0",
    description="Local-first advisory API for SafeCO event and plant monitoring.",
    lifespan=lifespan,
)

app.include_router(health_router, prefix="/api")
app.include_router(event_router, prefix="/api")
app.include_router(alert_router, prefix="/api")
app.include_router(plant_state_router, prefix="/api")
app.include_router(scenario_router, prefix="/api")
