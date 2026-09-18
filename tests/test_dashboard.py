"""Tests for the SafeCO operator dashboard.

The dashboard is a local, advisory operator console with tabbed views for each
concern (plant, alerts, events, scenarios). These tests pin the route wiring, the
tabbed structure, and the design constraints: served from the app, wired to the
real API endpoints, white content background, a flat multi-colour palette with a
single subtle tank-fill gradient, and no implied automatic action.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree

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
    """Adupe is presented as the fixed fictional demo facility."""
    body = client.get("/").text
    assert "Adupe Municipal Water Station" in body
    assert "Fictional demo facility" in body


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


def test_dashboard_has_pagination_controls() -> None:
    """Events and Alerts expose a per-page size selector and page nav."""
    body = client.get("/").text
    # A page-size selector per paginated view, offering 5/10/20/50/All.
    assert body.count("data-page-size") >= 2
    for size in ("5", "10", "20", "50", "all"):
        assert f'value="{size}"' in body
    # Prev/next page controls per paginated view.
    assert body.count("data-page-prev") >= 2
    assert body.count("data-page-next") >= 2


def test_dashboard_script_implements_pagination() -> None:
    """The client paginates client-side over the fetched list."""
    script = client.get("/static/app.js").text
    assert "pageSize" in script
    assert "page" in script


def test_dashboard_alerts_view_supports_ack_filter_and_id_search() -> None:
    """Operators can view acknowledged alerts and search by alert id."""
    body = client.get("/").text
    for f in ("all", "unacknowledged", "acknowledged"):
        assert f'data-filter="{f}"' in body
    assert 'id="alert-search"' in body


def test_dashboard_site_identity_is_not_editable() -> None:
    """The single supported demo site is rendered as text, not an input."""
    body = client.get("/").text
    assert 'id="site-name"' in body
    assert '<input id="site-name"' not in body


def test_dashboard_script_copies_ids_without_site_local_storage() -> None:
    """The client can copy alert IDs without relabelling the fixed site."""
    script = client.get("/static/app.js").text
    assert "localStorage" not in script
    assert "clipboard" in script
    # Uses the acknowledged endpoint or client-side ack filtering.
    assert "acknowledged" in script


def test_dashboard_events_use_a_scenario_selector() -> None:
    """The event filter offers registered choices instead of exact text input."""
    body = client.get("/").text
    assert '<select id="event-scenario-filter">' in body
    assert '<option value="">All scenarios</option>' in body


def test_dashboard_labels_the_high_level_limit() -> None:
    """The plant view explains the high-level safety limit and tank visualisation."""
    body = client.get("/").text
    assert 'data-field="high_level_limit"' in body
    assert 'class="tank-visual"' in body
    assert 'data-field="tank_water"' in body
    assert 'data-field="tank_status"' in body


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


def test_dashboard_script_consumes_the_live_stream() -> None:
    """The console is pushed to, not polling.

    The dashboard used to re-fetch four endpoints every two seconds, so a new
    finding could sit invisible for up to two seconds and every console paid for
    its own polling. It now renders from the live stream, and the timer that
    drove that polling is gone.
    """
    script = client.get("/static/app.js").text
    assert "EventSource" in script
    assert "/api/stream" in script
    assert "setInterval(refresh" not in script


def test_dashboard_script_handles_both_stream_frames() -> None:
    """The stream opens with a snapshot and pushes updates; both must render.

    A dropped stream is also the client's only signal that SafeCO itself is
    unreachable, since no server-side payload can report on its own behalf.
    """
    script = client.get("/static/app.js").text
    assert '"snapshot"' in script
    assert '"update"' in script
    assert "onerror" in script


def test_dashboard_script_keeps_a_manual_refresh() -> None:
    """The operator can still force a re-read without waiting for a push."""
    script = client.get("/static/app.js").text
    assert "refresh-btn" in script
    assert "async function refresh" in script


def test_dashboard_script_filters_events_without_refetching() -> None:
    """The stream carries one unfiltered window, so the filter runs locally.

    Refetching per keystroke would also be pointless: the pushed payload is the
    same window the filtered request would return.
    """
    script = client.get("/static/app.js").text
    assert "filterEvents" in script
    assert "scenario_id=" not in script


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
    """White content background, multi-colour palette, flat design.

    Severity/status colours and a tab accent are expected — a broader
    palette than plain grayscale, still using flat solid fills. A subtle
    single-hue gradient on the tank water fill is acceptable for
    visual clarity.
    """
    css = client.get("/static/styles.css").text
    lower = css.lower()
    assert "#fff" in lower or "#ffffff" in lower or "white" in lower
    # A few more colours than plain grayscale: expect several distinct hex codes.
    hexes = {h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}", css)}
    assert len(hexes) >= 6, f"expected a broader palette, found {sorted(hexes)}"


def test_dashboard_sidebar_header_uses_logo_lockup() -> None:
    """The brand row pairs the icon mark with the wordmark, subtitle below."""
    body = client.get("/").text
    assert 'class="brand-lockup"' in body
    lockup = body.split('class="brand-lockup"', 1)[1].split("</div>", 1)[0]
    # Transparent inline SVG mark (no boxed backing) beside the wordmark.
    assert "<svg" in lockup
    assert 'class="product">Safe<span' in lockup
    assert "<rect" not in lockup
    # Subtitle stays directly below the full lockup row.
    assert 'class="brand-sub">advisory command monitor<' in body


def test_dashboard_sidebar_mark_uses_brand_colours() -> None:
    """The sidebar mark keeps the hard hat and highlight palette."""
    body = client.get("/").text
    lockup = body.split('class="brand-lockup"', 1)[1].split("</div>", 1)[0]
    assert 'fill="#F5A623"' in lockup
    assert 'stroke="#FFD98E"' in lockup


def test_dashboard_favicon_is_boxed_navy_mark() -> None:
    """The browser tab icon is the icon-only boxed navy variant."""
    response = client.get("/static/favicon.svg")
    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]
    root = ElementTree.fromstring(response.content)
    rects = [el for el in root.iter() if el.tag.endswith("rect")]
    assert len(rects) == 1
    fill = rects[0].get("fill", "").lower()
    assert fill == "#101826"
    assert rects[0].get("rx") is not None
    assert 'fill="#F5A623"' in response.text
    # The HTML head points at the favicon.
    assert "/static/favicon.svg" in client.get("/").text
