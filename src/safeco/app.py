"""SafeCO FastAPI application."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from safeco.api.routes.alert_router import router as alert_router
from safeco.api.routes.event_router import router as event_router
from safeco.api.routes.health_router import router as health_router
from safeco.api.routes.plant_state_router import router as plant_state_router
from safeco.api.routes.scenario_router import router as scenario_router
from safeco.storage import EventStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the shared store and alert state at app startup."""
    app.state.store = EventStore("data/safeco.db")
    app.state.alerts: list[dict[str, object]] = []
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
