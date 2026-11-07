"""Настройки приложения. Все значения берутся из переменных окружения."""
import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    redis_host: str
    redis_port: int
    redis_db: int
    slow_threshold_ms: int
    worker_consumer: str
    worker_block_ms: int
    stream_maxlen: int


def get_settings() -> Settings:
    return Settings(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=_int_env("REDIS_PORT", 6379),
        redis_db=_int_env("REDIS_DB", 0),
        slow_threshold_ms=_int_env("SLOW_THRESHOLD_MS", 500),
        worker_consumer=os.getenv("WORKER_CONSUMER", "worker-1"),
        worker_block_ms=_int_env("WORKER_BLOCK_MS", 2000),
        stream_maxlen=_int_env("STREAM_MAXLEN", 100000),
    )
