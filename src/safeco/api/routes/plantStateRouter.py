from fastapi import APIRouter


router = APIRouter()


# Plant State
# GET a snapshot of current plant conditions (tank level, pump state, valve states, power source, operating mode)
@router.get("/plant_state")
async def plant_state():
    return
