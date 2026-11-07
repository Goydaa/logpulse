from app import store
from app.parser import parse_line
from tests.conftest import GOOD_LINES


def publish(r, lines):
    events = [parse_line(x) for x in lines]
    store.publish_events(r, events)
    return events


def test_publish_adds_to_stream_and_queued_counter(redis_client):
    publish(redis_client, GOOD_LINES)
    assert redis_client.xlen(store.STREAM) == 3
    assert int(redis_client.get(store.KEY_QUEUED)) == 3
    assert redis_client.type(store.STREAM) == "stream"


def test_counters_accumulate_after_worker(redis_client, worker):
    publish(redis_client, GOOD_LINES)
    assert worker.process_batch() == 3
    assert redis_client.hgetall(store.KEY_LEVEL) == {"INFO": "1", "ERROR": "1", "WARN": "1"}
    assert redis_client.hgetall(store.KEY_SERVICE) == {"auth": "1", "orders": "1", "payment": "1"}
    assert redis_client.hgetall(store.KEY_STATUS) == {"200": "1", "503": "1", "429": "1"}
    assert int(redis_client.get(store.KEY_TOTAL)) == 3


def test_queued_differs_from_processed_before_worker(redis_client, client):
    publish(redis_client, GOOD_LINES)
    data = client.get("/stats").json()
    assert data["queued_total"] == 3
    assert data["processed_total"] == 0
    assert data["backlog"] == 3


def test_message_acked_only_after_processing(redis_client, worker):
    publish(redis_client, GOOD_LINES)
    # прочитано, но worker ещё не обработал: сообщения висят в pending
    redis_client.xreadgroup(store.GROUP, "test-worker", {store.STREAM: ">"}, count=10)
    assert redis_client.xpending(store.STREAM, store.GROUP)["pending"] == 3
    # после обработки pending пуст
    assert worker.recover_pending() == 3
    assert redis_client.xpending(store.STREAM, store.GROUP)["pending"] == 0


def test_slow_requests_sorted_by_duration(redis_client, worker):
    lines = [
        "2026-10-20T12:00:01Z INFO auth 192.0.2.10 GET /api/profile 200 499ms rid=00000001",
        "2026-10-20T12:00:02Z WARN orders 192.0.2.10 GET /api/orders 200 500ms rid=00000002",
        "2026-10-20T12:00:03Z ERROR payment 192.0.2.10 POST /api/pay 504 2400ms rid=00000003",
        "2026-10-20T12:00:04Z ERROR orders 192.0.2.10 GET /api/orders 503 900ms rid=00000004",
    ]
    publish(redis_client, lines)
    worker.process_batch()
    top = redis_client.zrevrange(store.KEY_SLOW, 0, -1, withscores=True)
    assert top == [("00000003", 2400.0), ("00000004", 900.0), ("00000002", 500.0)]
    assert redis_client.type(store.KEY_SLOW) == "zset"


def test_top_slow_limited_to_five(redis_client, worker):
    lines = [
        f"2026-10-20T12:00:{i:02d}Z ERROR orders 192.0.2.10 GET /api/orders 503 {600 + i * 10}ms rid={i:08x}"
        for i in range(1, 9)
    ]
    publish(redis_client, lines)
    worker.process_batch()
    top = store.get_stats(redis_client)["top_slow"]
    assert len(top) == 5
    assert [t["duration_ms"] for t in top] == [680, 670, 660, 650, 640]


def test_duplicate_delivery_does_not_double_count(redis_client, worker):
    publish(redis_client, GOOD_LINES[:1])
    publish(redis_client, GOOD_LINES[:1])  # тот же rid второй раз
    worker.process_batch()
    assert int(redis_client.get(store.KEY_TOTAL)) == 1
    assert redis_client.hget(store.KEY_LEVEL, "INFO") == "1"


def test_broken_message_is_acked_and_skipped(redis_client, worker):
    redis_client.xadd(store.STREAM, {"level": "INFO"})
    publish(redis_client, GOOD_LINES[:1])
    assert worker.process_batch() == 2
    assert int(redis_client.get(store.KEY_TOTAL)) == 1
    assert redis_client.xpending(store.STREAM, store.GROUP)["pending"] == 0
