from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["scenarios"])


@router.get("/scenarios")
async def list_scenarios() -> list[str]:
    """List the known scenario identifiers.

    This is a placeholder until the scenario runner is fully exposed through the
    API.
    """
    return [
        "startup_01",
        "steady_running_01",
        "controlled_shutdown_01",
        "grid_recovery_01",
        "maintenance_01",
        "extended_normal_01",
    ]


@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str) -> dict[str, str]:
    """Return a scenario placeholder for UI integration."""
    return {"scenario_id": scenario_id, "status": "not_implemented"}
