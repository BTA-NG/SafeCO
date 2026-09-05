"""Tests for the SafeCO operator dashboard.

The dashboard is a plain, local, advisory operator page. These tests pin the
route wiring and the design constraints agreed for it: served from the app,
wired to the real API endpoints, white background, and no gradients or implied
automatic action.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from safeco.app import app

client = TestClient(app)


def test_dashboard_index_is_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "SafeCO" in body
    assert "Adupe" in body
    # Structural hooks the client script renders into.
    for element_id in (
        "health-banner",
        "plant-state",
        "events",
        "alerts",
        "scenario-controls",
    ):
        assert f'id="{element_id}"' in body


def test_dashboard_script_calls_the_real_api() -> None:
    response = client.get("/static/app.js")
    assert response.status_code == 200
    script = response.text
    for endpoint in (
        "/api/health",
        "/api/plant/state",
        "/api/events",
        "/api/alerts",
        "/api/scenarios",
    ):
        assert endpoint in script
    # Acknowledgement is recorded via the ack endpoint, not a plant action.
    assert "/ack" in script


def test_dashboard_indicates_degraded_visibility_when_feed_lost() -> None:
    """Offline story: the page must be able to show degraded visibility."""
    body = client.get("/").text
    script = client.get("/static/app.js").text
    assert "degraded" in (body + script).lower()


def test_dashboard_never_implies_automatic_action() -> None:
    """SafeCO is advisory; the UI must not claim it acted on the plant."""
    body = client.get("/").text.lower()
    assert "advisory" in body
    for forbidden in ("automatically blocked", "safeco stopped", "shut down the pump"):
        assert forbidden not in body


def test_dashboard_styles_are_plain() -> None:
    """Design constraint: white background, no gradients."""
    css = client.get("/static/styles.css")
    assert css.status_code == 200
    text = css.text.lower()
    assert "gradient" not in text
    assert "#fff" in text or "#ffffff" in text or "white" in text
