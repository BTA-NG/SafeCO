"""Tests for the scenario execution endpoint.

Running a scenario through the API must persist its events to the event store,
run the detector, and persist any alerts to the alert store, so the dashboard can
show a scenario and its explained findings end to end.
"""

from __future__ import annotations


def test_run_unknown_scenario_returns_404(client) -> None:
    response = client.post("/api/scenarios/does_not_exist/run")
    assert response.status_code == 404


def test_run_normal_scenario_persists_events(client, event_store) -> None:
    """A normal scenario should persist events and produce no alerts."""
    response = client.post("/api/scenarios/startup_01/run", params={"seed": 42})
    assert response.status_code == 200
    body = response.json()

    assert body["scenario_id"] == "startup_01"
    assert body["seed"] == 42
    assert body["ground_truth"] == "normal"
    assert body["events"] > 0
    assert body["alerts"] == 0
    assert "fingerprint" in body

    # Events are actually in the store and readable through the events API.
    assert len(event_store.list_events(limit=100)) == body["events"]
    listed = client.get("/api/events", params={"scenario_id": "startup_01"})
    assert len(listed.json()) == body["events"]


def test_run_attack_scenario_persists_alerts(client) -> None:
    """The injection attack (pump start, inlet closed) should raise an alert."""
    response = client.post(
        "/api/scenarios/attack_injection_01/run", params={"seed": 42}
    )
    assert response.status_code == 200
    body = response.json()

    assert body["ground_truth"] == "injection"
    assert body["alerts"] >= 1

    # Alerts are persisted and served through the alerts API.
    alerts = client.get("/api/alerts").json()
    assert len(alerts) >= 1
    reason_codes = {a["reason_code"] for a in alerts}
    assert "unsafe_pump_start" in reason_codes
    # Advisory only: the alert recommends a human step, never claims action taken.
    unsafe = next(a for a in alerts if a["reason_code"] == "unsafe_pump_start")
    assert unsafe["recommended_action"]
    assert unsafe["acknowledged"] is False


def test_run_is_deterministic_on_seed(client) -> None:
    """Same seed => same fingerprint, so a judge can reproduce a run."""
    first = client.post("/api/scenarios/startup_01/run", params={"seed": 7}).json()
    second = client.post("/api/scenarios/startup_01/run", params={"seed": 7}).json()
    assert first["fingerprint"] == second["fingerprint"]


def test_run_fingerprint_matches_canonical_run_scenario(client) -> None:
    """Guard against execution drift between the endpoint and run_scenario.

    The endpoint must execute the scenario identically to
    ``scenarios.run_scenario``, so its fingerprint matches the canonical path.
    """
    from safeco.scenarios import run_scenario, scenario_fingerprint

    endpoint = client.post("/api/scenarios/startup_01/run", params={"seed": 5}).json()
    canonical = scenario_fingerprint(run_scenario("startup_01", seed=5))
    assert endpoint["fingerprint"] == canonical


def test_run_jitter_variant_composes_canonical_run_scenario(client) -> None:
    """A timing-jitter attack variant runs via POST and matches run_scenario.

    The jitter variants live only in ``ATTACK_JITTER_SCENARIOS`` and reuse their
    base attack's steps; only the registered ``DURATION_JITTER`` plan differs.
    The endpoint must compose ``run_scenario`` (not re-implement the step loop
    against a partial registry), so:

    * the variant is runnable at all — the old hand-rolled registry 404'd it;
    * its fingerprint matches the canonical ``run_scenario`` for that id; and
    * applying the jitter plan makes its trace diverge from the un-jittered
      base at the same seed (proof the plan is actually applied, not dropped).
    """
    from safeco.scenarios import run_scenario, scenario_fingerprint

    response = client.post(
        "/api/scenarios/attack_injection_jitter_01/run", params={"seed": 7}
    )
    assert response.status_code == 200
    jitter = response.json()
    assert jitter["scenario_id"] == "attack_injection_jitter_01"
    assert jitter["ground_truth"] == "injection"

    canonical = scenario_fingerprint(run_scenario("attack_injection_jitter_01", seed=7))
    assert jitter["fingerprint"] == canonical

    base = client.post(
        "/api/scenarios/attack_injection_01/run", params={"seed": 7}
    ).json()
    assert jitter["fingerprint"] != base["fingerprint"]
