from app import store
from tests.conftest import BAD_LINES, GOOD_LINES


def test_ingest_mixed_batch(client, redis_client):
    body = {"lines": [GOOD_LINES[0], BAD_LINES[0], GOOD_LINES[1], BAD_LINES[1], GOOD_LINES[2]]}
    resp = client.post("/ingest", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 3
    assert data["rejected"] == 2
    assert [e["line_number"] for e in data["errors"]] == [2, 4]
    assert data["errors"][0]["code"] == "bad_timestamp"
    assert data["errors"][1]["code"] == "bad_ip"
    # некорректные строки в очередь не попали
    assert redis_client.xlen(store.STREAM) == 3


def test_ingest_wrong_schema_returns_422(client):
    resp = client.post("/ingest", json={"lines": "не список"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_ingest_missing_field_returns_422(client):
    assert client.post("/ingest", json={}).status_code == 422


def test_ingest_empty_list_returns_422(client):
    assert client.post("/ingest", json={"lines": []}).status_code == 422


def test_ingest_more_than_100_lines_rejected(client):
    resp = client.post("/ingest", json={"lines": [GOOD_LINES[0]] * 101})
    assert resp.status_code == 422


def test_ingest_exactly_100_lines_allowed(client):
    resp = client.post("/ingest", json={"lines": [GOOD_LINES[0]] * 100})
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 100


def test_ingest_line_too_long_returns_422(client):
    assert client.post("/ingest", json={"lines": ["x" * 501]}).status_code == 422


def test_ingest_empty_string_returns_422(client):
    assert client.post("/ingest", json={"lines": [""]}).status_code == 422


def test_422_does_not_echo_input(client):
    resp = client.post("/ingest", json={"lines": "секретное-значение"})
    assert "секретное-значение" not in resp.text


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "api": "up", "redis": "up"}


def test_health_returns_503_when_redis_down(down_client):
    resp = down_client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["redis"] == "down"
    assert body["api"] == "up"
    assert body["error"]["code"] == "redis_unavailable"


def test_stats_returns_503_when_redis_down(down_client):
    resp = down_client.get("/stats")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "redis_unavailable"
    assert "Traceback" not in resp.text


def test_ingest_returns_503_when_redis_down(down_client):
    resp = down_client.post("/ingest", json={"lines": GOOD_LINES})
    assert resp.status_code == 503


def test_stats_after_worker(client, redis_client, worker):
    client.post("/ingest", json={"lines": GOOD_LINES})
    worker.process_batch()
    data = client.get("/stats").json()
    assert data["queued_total"] == 3
    assert data["processed_total"] == 3
    assert data["backlog"] == 0
    assert data["by_level"] == {"ERROR": 1, "INFO": 1, "WARN": 1}
    assert data["by_status"] == {"200": 1, "429": 1, "503": 1}
    assert data["top_slow"] == [{"rid": "ee44cc22", "duration_ms": 742}]
    assert data["slow_threshold_ms"] == 500


def test_stats_empty_redis(client):
    data = client.get("/stats").json()
    assert data["processed_total"] == 0
    assert data["top_slow"] == []


def test_events_limit(client):
    client.post("/ingest", json={"lines": GOOD_LINES})
    data = client.get("/events", params={"limit": 2}).json()
    assert data["count"] == 2
    # новые записи идут первыми
    assert data["events"][0]["rid"] == "ff44aa33"
    assert data["events"][0]["status"] == 429


def test_events_default_limit(client):
    client.post("/ingest", json={"lines": GOOD_LINES})
    assert client.get("/events").json()["count"] == 3


def test_events_limit_out_of_range(client):
    assert client.get("/events", params={"limit": 0}).status_code == 422
    assert client.get("/events", params={"limit": 51}).status_code == 422
    assert client.get("/events", params={"limit": "abc"}).status_code == 422


def test_unknown_route_uses_unified_error_format(client):
    resp = client.get("/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "http_error"


def test_openapi_and_docs_available(client):
    schema = client.get("/openapi.json").json()
    assert {"/health", "/ingest", "/stats", "/events"} <= set(schema["paths"])
    assert client.get("/docs").status_code == 200
