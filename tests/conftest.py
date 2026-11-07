import fakeredis
import pytest
import redis
from fastapi.testclient import TestClient

from app import store
from app.main import create_app
from app.redis_client import get_redis

GOOD_LINES = [
    "2026-10-20T12:34:56Z INFO auth 192.0.2.10 POST /api/login 200 43ms rid=ab12cd34",
    "2026-10-20T12:34:58Z ERROR orders 198.51.100.8 GET /api/orders 503 742ms rid=ee44cc22",
    "2026-10-20T12:35:01Z WARN payment 203.0.113.7 POST /api/pay 429 301ms rid=ff44aa33",
]
BAD_LINES = [
    "2026-13-20T12:34:56Z INFO auth 192.0.2.10 POST /api/login 200 43ms rid=aa000001",
    "2026-10-20T12:34:56Z INFO auth 192.0.2.300 POST /api/login 200 43ms rid=aa000002",
]


class DownRedis:
    """Имитация недоступного Redis: любое обращение даёт ConnectionError."""

    def __getattr__(self, name):
        raise redis.exceptions.ConnectionError("simulated outage")


@pytest.fixture
def redis_client():
    # отдельный in-memory сервер на каждый тест, рабочий Redis не затрагивается
    server = fakeredis.FakeServer()
    return fakeredis.FakeRedis(server=server, decode_responses=True)


@pytest.fixture
def client(redis_client):
    app = create_app()
    app.dependency_overrides[get_redis] = lambda: redis_client
    return TestClient(app)


@pytest.fixture
def down_client():
    app = create_app()
    app.dependency_overrides[get_redis] = lambda: DownRedis()
    return TestClient(app)


@pytest.fixture
def worker(redis_client):
    from app.worker import Worker

    w = Worker(redis_client, consumer="test-worker")
    w.ensure_group()
    return w
