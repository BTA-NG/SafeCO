from fastapi import APIRouter
from events.py import ProcessSnapshot


router = APIRouter()

# Events list (to get all the events in the DB currently)
# a GET request
# Try to add filtering by scenario ID or try to check if it's possible
# GET a specific event by ID
# GET  events after a given event ID (because of the dashboard)
