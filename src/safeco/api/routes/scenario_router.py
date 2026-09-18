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
from safeco.scenarios import runnable_scenarios

router = APIRouter(tags=["scenarios"])


@router.get("/scenarios")
async def list_scenarios() -> list[str]:
    """List every scenario the dashboard picker offers.

    Resolved against ``runnable_scenarios`` — the same set the run and detail
    routes accept — so the picker can never offer an id the run route would
    refuse, nor hide one it would accept.

    Returns:
        A sorted list of scenario id strings.

    """
    return sorted(runnable_scenarios())


@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str) -> dict[str, str]:
    """Return metadata confirming a scenario id is known.

    Used to validate a scenario id before running it. Execution is a separate
    POST so a read of this route never changes state. The id is checked against
    the full runnable set (``runnable_scenarios``) — the same set the run route
    uses — so this never 404s an id that ``POST /scenarios/{id}/run`` would
    accept.

    Args:
        scenario_id: The registry key to look up.

    Returns:
        A dict with the scenario id and a ``registered`` status.

    Raises:
        HTTPException: 404 if the id is not in the runnable scenario set.

    """
    if scenario_id not in runnable_scenarios():
        raise HTTPException(
            status_code=404, detail=f"scenario {scenario_id!r} not found"
        )
    return {"scenario_id": scenario_id, "status": "registered"}


@router.post("/scenarios/{scenario_id}/run")
def run_scenario_endpoint(
    scenario_id: str,
    store: StoreDep,
    alert_store: AlertStoreDep,
    seed: int = Query(default=42, ge=0),
) -> dict[str, object]:
    """Run a scenario and persist its events and detector alerts.

    Drives the simulator through the named scenario, stores each command as an
    event, runs the detector over the growing history, and persists any
    findings. This is how the dashboard produces an end-to-end demonstration
    (command -> event -> detection -> alert) on demand. It is advisory only: the
    run demonstrates consequences and never acts on a real plant.

    Args:
        scenario_id: The scenario registry key to execute.
        store: The shared event store the run writes events to.
        alert_store: The shared alert store the run writes findings to.
        seed: Deterministic RNG seed so a run is reproducible.

    Returns:
        A summary dict: scenario id, seed, ground truth, event count, distinct
        alert count, invariant violations, and the reproducibility fingerprint.

    Raises:
        HTTPException: 404 if the scenario id is unknown.

    """
    try:
        return run_scenario_and_persist(scenario_id, seed, store, alert_store)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"scenario {scenario_id!r} not found"
        ) from exc
