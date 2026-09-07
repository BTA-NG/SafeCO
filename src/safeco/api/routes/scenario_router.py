"""Scenario registry endpoints for the SafeCO API.

Endpoints provide scenario discovery and metadata. Scenario execution
(run_scenario) is intentionally deferred and documented as future work.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from safeco.scenarios import ATTACK_SCENARIOS, NORMAL_SCENARIOS

router = APIRouter(tags=["scenarios"])


@router.get("/scenarios")
async def list_scenarios() -> list[str]:
    """List all known scenario identifiers.

    Returns both normal and attack scenario IDs from the scenario registries.
    Scenario execution is deferred and not yet exposed through the API.
    """
    all_scenarios = {**NORMAL_SCENARIOS, **ATTACK_SCENARIOS}
    return sorted(all_scenarios.keys())


@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str) -> dict[str, str]:
    """Return scenario metadata.

    Returns 404 if the scenario ID is not found in either the normal or
    attack scenario registry. Scenario execution is deferred and not yet
    implemented.
    """
    all_scenarios = {**NORMAL_SCENARIOS, **ATTACK_SCENARIOS}
    if scenario_id not in all_scenarios:
        raise HTTPException(
            status_code=404, detail=f"scenario {scenario_id!r} not found"
        )
    return {"scenario_id": scenario_id, "status": "registered"}
