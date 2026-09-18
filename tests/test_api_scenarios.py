"""Tests for the SafeCO scenario registry API endpoints."""

from __future__ import annotations

from safeco.scenarios import (
    ATTACK_JITTER_SCENARIOS,
    ATTACK_SCENARIOS,
    NORMAL_SCENARIOS,
)


def test_scenario_list_includes_all_scenarios(client) -> None:
    """The scenario list should return all known scenario IDs."""
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    scenarios = response.json()

    # Verify all NORMAL_SCENARIOS are included
    for scenario_id in NORMAL_SCENARIOS:
        assert scenario_id in scenarios

    # Verify all ATTACK_SCENARIOS are included
    for scenario_id in ATTACK_SCENARIOS:
        assert scenario_id in scenarios

    for scenario_id in ATTACK_JITTER_SCENARIOS:
        assert scenario_id in scenarios


def test_scenario_list_sorted_and_complete(client) -> None:
    """The scenario list should be sorted and match the full registry."""
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    scenarios = response.json()

    all_scenarios = {
        **NORMAL_SCENARIOS,
        **ATTACK_SCENARIOS,
        **ATTACK_JITTER_SCENARIOS,
    }
    assert scenarios == sorted(all_scenarios.keys())


def test_scenario_detail_returns_registered_for_known_id(client) -> None:
    """A known scenario ID should return a registered status."""
    # Pick the first scenario from NORMAL_SCENARIOS
    scenario_id = list(NORMAL_SCENARIOS.keys())[0]

    response = client.get(f"/api/scenarios/{scenario_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario_id"] == scenario_id
    assert payload["status"] == "registered"


def test_scenario_detail_returns_404_for_unknown_id(client) -> None:
    """An unknown scenario ID should return a 404."""
    response = client.get("/api/scenarios/unknown_scenario_xyz")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_scenario_detail_validates_attack_scenarios(client) -> None:
    """Attack scenario IDs should also be valid and return registered."""
    # Pick the first scenario from ATTACK_SCENARIOS
    scenario_id = list(ATTACK_SCENARIOS.keys())[0]

    response = client.get(f"/api/scenarios/{scenario_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario_id"] == scenario_id
    assert payload["status"] == "registered"


def test_scenario_detail_validates_jitter_variants(client) -> None:
    """Jitter variants are runnable, so the detail route must validate them.

    ``POST /scenarios/{id}/run`` drives the canonical runner, which accepts the
    timing-jitter variants. The detail route validates an id before a run, so it
    must accept exactly what the runner accepts; otherwise the API 404s an id it
    would happily run.
    """
    scenario_id = list(ATTACK_JITTER_SCENARIOS.keys())[0]

    response = client.get(f"/api/scenarios/{scenario_id}")
    assert response.status_code == 200
    assert response.json() == {
        "scenario_id": scenario_id,
        "status": "registered",
    }
