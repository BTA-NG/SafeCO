from fastapi.testclient import TestClient

from safeco.app import app

client = TestClient(app)


def test_app_registers_expected_routes() -> None:
    """The FastAPI app should expose the core dashboard routes."""
    paths = {route.path for route in app.routes}
    assert "/api/health" in paths
    assert "/api/events" in paths
    assert "/api/alerts" in paths
    assert "/api/plant/state" in paths


def test_app_health_route_is_accessible() -> None:
    """The health route should answer successfully."""
    response = client.get("/api/health")
    assert response.status_code == 200
