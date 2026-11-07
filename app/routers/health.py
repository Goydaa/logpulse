from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from redis import Redis
from redis.exceptions import RedisError

from app.redis_client import get_redis
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Redis недоступен"}},
    summary="Доступность API и Redis",
)
def health(r: Redis = Depends(get_redis)):
    try:
        r.ping()
    except RedisError:
        body = HealthResponse(
            status="unavailable",
            api="up",
            redis="down",
            error={"code": "redis_unavailable", "message": "Нет связи с Redis"},
        )
        return JSONResponse(status_code=503, content=body.model_dump(exclude_none=True))
    body = HealthResponse(status="ok", api="up", redis="up")
    return JSONResponse(status_code=200, content=body.model_dump(exclude_none=True))
