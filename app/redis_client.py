"""Создание клиента Redis и зависимость FastAPI."""
from fastapi import Request
from redis import Redis

from app.config import Settings, get_settings


def create_redis(settings: Settings | None = None, socket_timeout: float = 3.0) -> Redis:
    """Клиент подключается лениво: приложение стартует и при недоступном Redis."""
    s = settings or get_settings()
    return Redis(
        host=s.redis_host,
        port=s.redis_port,
        db=s.redis_db,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=socket_timeout,
        health_check_interval=15,
    )


def get_redis(request: Request) -> Redis:
    """Зависимость FastAPI. В тестах подменяется через dependency_overrides."""
    return request.app.state.redis
