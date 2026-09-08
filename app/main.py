import sys
from pathlib import Path

# Add project root directory to sys.path so 'app' package imports work cleanly
# regardless of whether the script is invoked from root or as a sub-path.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.settings import get_settings
from app.routes.analyse import router as analyse_router
from app.routes.health import router as health_router
from app.routes.time import router as time_router


settings = get_settings()

app = FastAPI(
    title="Anthos AI Server",
    description="A lightweight FastAPI server for health, time, and email analysis.",
    version="1.0.0",
)

# Enable CORS restricted to anthosweb URL from env
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, tags=["Health"])
app.include_router(time_router, tags=["Time"])
app.include_router(analyse_router, tags=["Analyse"])

main = app