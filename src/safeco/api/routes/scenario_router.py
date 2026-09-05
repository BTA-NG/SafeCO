"""Scenario registry endpoints for the SafeCO API.

Endpoints provide scenario discovery, metadata, and execution. Running a
scenario persists its events and any detector alerts so the dashboard can
show a scenario end to end. SafeCO stays advisory: running a scenario drives
the simulator to demonstrate consequences and never acts on a real plant.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from safeco.api.deps import AlertStoreDep, StoreDep
from safeco.api.scenario_runner import run_scenario_and_persist
from safeco.scenarios import ATTACK_SCENARIOS, NORMAL_SCENARIOS

router = APIRouter(tags=["scenarios"])


@router.get("/scenarios")
async def list_scenarios() -> list[str]:
    """List all known scenario identifiers.

    Returns both normal and attack scenario IDs from the scenario registries.
    """
    all_scenarios = {**NORMAL_SCENARIOS, **ATTACK_SCENARIOS}
    return sorted(all_scenarios.keys())


@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str) -> dict[str, str]:
    """Return scenario metadata.

    Returns 404 if the scenario ID is not found in either the normal or
    attack scenario registry.
    """
    all_scenarios = {**NORMAL_SCENARIOS, **ATTACK_SCENARIOS}
    if scenario_id not in all_scenarios:
        raise HTTPException(
            status_code=404, detail=f"scenario {scenario_id!r} not found"
        )
    return {"scenario_id": scenario_id, "status": "registered"}


@router.post("/scenarios/{scenario_id}/run")
async def run_scenario_endpoint(
    scenario_id: str,
    store: StoreDep,
    alert_store: AlertStoreDep,
    seed: int = Query(default=42, ge=0),
) -> dict[str, object]:
    """Run a scenario, persisting its events and detector alerts.

    Drives the simulator through the scenario, stores each command as an event,
    runs the detector over the growing history, and persists any findings. The
    response summarises the run (events, alerts, violations, reproducibility
    fingerprint). Returns 404 for an unknown scenario id.
    """
    try:
        return run_scenario_and_persist(scenario_id, seed, store, alert_store)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"scenario {scenario_id!r} not found"
        ) from exc
