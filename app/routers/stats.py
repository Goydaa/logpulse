from fastapi import APIRouter, Depends
from redis import Redis

from app import store
from app.config import get_settings
from app.redis_client import get_redis
from app.schemas import ErrorResponse, StatsResponse

router = APIRouter(tags=["stats"])


@router.get(
    "/stats",
    response_model=StatsResponse,
    responses={503: {"model": ErrorResponse, "description": "Redis недоступен"}},
    summary="Агрегированная статистика",
)
def stats(r: Redis = Depends(get_redis)):
    data = store.get_stats(r, top=5)
    data["slow_threshold_ms"] = get_settings().slow_threshold_ms
    return data
