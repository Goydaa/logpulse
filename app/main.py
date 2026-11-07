"""Точка входа FastAPI: uvicorn app.main:app"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.errors import register_error_handlers
from app.redis_client import create_redis
from app.routers import events, health, ingest, stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app.state.redis = create_redis()
    yield
    app.state.redis.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="LogPulse",
        version=__version__,
        description="Приём логов, проверка формата, очередь в Redis Streams и статистика.",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(stats.router)
    app.include_router(events.router)
    register_error_handlers(app)
    return app


app = create_app()
