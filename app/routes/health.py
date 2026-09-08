from fastapi import APIRouter
from app.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
