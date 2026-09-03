"""SafeCO FastAPI application."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from safeco.api.routes.alertRouter import router as alert_router
from safeco.api.routes.eventRouter import router as event_router
from safeco.api.routes.healthRouter import router as health_router
from safeco.api.routes.plantStateRouter import router as plant_state_router
from safeco.api.routes.scenarioRouter import router as scenario_router
from safeco.storage import EventStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the shared store at app startup and close it on shutdown."""
    app.state.store = EventStore("data/safeco.db")
    try:
        yield
    finally:
        app.state.store.close()


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
