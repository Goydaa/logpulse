from fastapi import APIRouter, Depends, Query
from redis import Redis

from app import store
from app.redis_client import get_redis
from app.schemas import ErrorResponse, EventsResponse

router = APIRouter(tags=["events"])


@router.get(
    "/events",
    response_model=EventsResponse,
    responses={
        422: {"model": ErrorResponse, "description": "limit вне диапазона 1-50"},
        503: {"model": ErrorResponse, "description": "Redis недоступен"},
    },
    summary="Последние записи Redis Stream",
)
def events(
    limit: int = Query(10, ge=1, le=50, description="Сколько записей вернуть"),
    r: Redis = Depends(get_redis),
):
    items = store.recent_events(r, limit)
    return {"count": len(items), "events": items}
