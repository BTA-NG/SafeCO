from __future__ import annotations

from fastapi.testclient import TestClient

from safeco.app import app


def test_app_registers_expected_routes() -> None:
    """The FastAPI app should expose the core dashboard routes."""
    paths = {route.path for route in app.routes}
    assert "/api/health" in paths
    assert "/api/events" in paths
    assert "/api/alerts" in paths
    assert "/api/plant/state" in paths


def test_app_health_route_is_accessible(client) -> None:
    """The health route should answer promptly through the running lifespan.

    The ``client`` fixture runs the app under a context-managed TestClient with
    the database pinned to a temp path, so the lifespan opens that store and this
    request never touches the real ``data/safeco.db``.
    """
    response = client.get("/api/health")
    assert response.status_code == 200


def test_lifespan_creates_and_closes_its_own_store(tmp_path, monkeypatch) -> None:
    """With no store injected, the lifespan opens one and closes it on exit.

    Points both databases at temp paths so the production files are untouched,
    and asserts the stores are created inside the context and torn down after.
    """
    monkeypatch.setenv("SAFECO_DATABASE", str(tmp_path / "lifespan.db"))
    monkeypatch.setenv("SAFECO_ALERT_DATABASE", str(tmp_path / "lifespan_alerts.db"))
    app.state.store = None
    app.state.alert_store = None
    with TestClient(app) as test_client:
        assert app.state.store is not None
        assert app.state.alert_store is not None
        assert test_client.get("/api/health").status_code == 200
    # Lifespan owns the stores here, so it must release them on shutdown.
    assert app.state.store is None
    assert app.state.alert_store is None
