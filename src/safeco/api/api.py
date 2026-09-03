import uvicorn
from api.routes.alertRouter import router as alert_router
from api.routes.eventRouter import router as event_router
from api.routes.healthRouter import router as health_router
from api.routes.plantStateRouter import router as plant_state_router
from api.routes.scenarioRouter import router as scenario_router
from fastapi import FastAPI

app = FastAPI()


app.include_router(health_router, prefix="/api/health")
app.include_router(alert_router, prefix="/api/alert")
app.include_router(event_router, prefix="/api/event")
app.include_router(plant_state_router, prefix="/api/plant/state")
app.include_router(scenario_router, prefix="/api/scenarios")




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=="0.0.0.0", port=7000)