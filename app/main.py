from fastapi import FastAPI

from app.routes.analyse import router as analyse_router
from app.routes.health import router as health_router
from app.routes.time import router as time_router


app = FastAPI(
    title="Anthos AI Server",
    description="A lightweight FastAPI server for health, time, and email analysis.",
    version="1.0.0",
)

app.include_router(health_router, tags=["Health"])
app.include_router(time_router, tags=["Time"])
app.include_router(analyse_router, tags=["Analyse"])