from datetime import datetime, timezone

from fastapi import APIRouter
from app.schemas import TimeResponse

router = APIRouter()


@router.get("/time", response_model=TimeResponse, summary="Current server UTC time")
def get_time() -> TimeResponse:
    now = datetime.now(tz=timezone.utc)
    return TimeResponse(utc_time=now.isoformat())
