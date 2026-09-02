from fastapi import APIRouter
from safeco.events import ProcessSnapshot

router = APIRouter()


# Health Status (to check if SafeCO is up and running) 
#  && Plant Status (To see the overall state of the plant)
# has to be a GET request
# another GET request here
# should check t see if the Modbus feed is active and the database is running

@router.get("/health")
async def health_stats():

    return
