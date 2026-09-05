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


def test_app_health_route_is_accessible(api_store) -> None:
    """The health route should answer promptly against the injected store.

    The autouse ``api_store`` fixture injects a temporary event store and
    overrides the ``get_store`` dependency, so this request never touches the
    real ``data/safeco.db`` file whose WAL lock could otherwise stall it.
    """
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200


def test_lifespan_creates_and_closes_its_own_store(tmp_path, monkeypatch) -> None:
    """With no store injected, the lifespan opens one and closes it on exit.

    Points the database at a temp path so production data/safeco.db is untouched,
    and asserts the store is created inside the context and torn down after.
    """
    monkeypatch.setenv("SAFECO_DATABASE", str(tmp_path / "lifespan.db"))
    app.state.store = None
    with TestClient(app) as client:
        assert app.state.store is not None
        assert client.get("/api/health").status_code == 200
    # Lifespan owns the store here, so it must release it on shutdown.
    assert app.state.store is None
