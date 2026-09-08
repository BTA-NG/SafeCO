"""Tests for the SafeCO operator dashboard.

The dashboard is a local, advisory operator console with tabbed views for each
concern (plant, alerts, events, scenarios). These tests pin the route wiring, the
tabbed structure, and the design constraints: served from the app, wired to the
real API endpoints, white content background, a flat multi-colour palette (no
gradients), and no implied automatic action.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from safeco.app import app

client = TestClient(app)


def test_dashboard_index_is_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "SafeCO" in body
    # Structural hooks the client script renders into.
    for element_id in (
        "health-banner",
        "plant-state",
        "events",
        "alerts",
        "scenario-controls",
    ):
        assert f'id="{element_id}"' in body


def test_dashboard_defaults_site_name_to_adupe_example() -> None:
    """Adupe remains the default example site, now as an editable default."""
    script = client.get("/static/app.js").text
    assert "Adupe" in script


def test_dashboard_has_tabbed_navigation() -> None:
    """The console exposes tabbed views, not one flat API dump."""
    body = client.get("/").text
    for view in ("plant", "alerts", "events", "scenarios", "health"):
        assert f'data-tab="{view}"' in body
    # A tab panel per view so navigation has something to show/hide.
    for view in ("plant", "alerts", "events", "scenarios", "health"):
        assert f'data-panel="{view}"' in body


def test_dashboard_has_health_view() -> None:
    """A dedicated system-health view surfaces feed status and counts."""
    body = client.get("/").text
    assert 'data-panel="health"' in body
    assert 'id="health-page"' in body


def test_dashboard_alerts_view_supports_ack_filter_and_id_search() -> None:
    """Operators can view acknowledged alerts and search by alert id."""
    body = client.get("/").text
    for f in ("all", "unacknowledged", "acknowledged"):
        assert f'data-filter="{f}"' in body
    assert 'id="alert-search"' in body


def test_dashboard_allows_renaming_the_site() -> None:
    """The monitored site name is editable, with no fixed 'example' label."""
    body = client.get("/").text
    assert 'id="site-name"' in body
    assert "example deployment" not in body.lower()


def test_dashboard_script_persists_name_and_copies_ids() -> None:
    """The client persists the site name and can copy an alert id."""
    script = client.get("/static/app.js").text
    assert "localStorage" in script
    assert "clipboard" in script
    # Uses the acknowledged endpoint or client-side ack filtering.
    assert "acknowledged" in script


def test_dashboard_script_supports_tab_switching() -> None:
    """The client wires tab navigation."""
    script = client.get("/static/app.js").text
    assert "data-tab" in script


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


def test_dashboard_styles_are_plain_but_colourful() -> None:
    """White content background and no gradients, but a flat multi-colour palette.

    Severity/status colours and a tab accent are expected — a broader palette than
    plain grayscale, still using flat solid fills only.
    """
    css = client.get("/static/styles.css").text
    lower = css.lower()
    assert "gradient" not in lower
    assert "#fff" in lower or "#ffffff" in lower or "white" in lower
    # A few more colours than plain grayscale: expect several distinct hex codes.
    hexes = {h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}", css)}
    assert len(hexes) >= 6, f"expected a broader palette, found {sorted(hexes)}"
