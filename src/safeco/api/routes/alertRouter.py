from fastapi import APIRouter


router = APIRouter()

# Alert Management (for everything related to alerts from SafeCO)
# GET all the recent alerts
# GET all the alerts that are not acknowledged or not attended to 
# POST to mark an alert as acknowledged by ID
# GET to filter alerts by severity or reason code
