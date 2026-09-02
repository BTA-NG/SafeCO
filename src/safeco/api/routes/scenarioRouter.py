from fastapi import APIRouter
from safeco.events import Event


router = APIRouter()


# Scenario Control
# start a scenario
# GET a scenario status
# GET all available scenarios

@router.get("/scenario/{id}")
async def single_scenario(event_id: int, event: Event):
    if 