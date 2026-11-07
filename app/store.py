"""Структуры Redis и операции над ними (общие для API и worker)."""
from redis import Redis

from app.config import get_settings

STREAM = "logpulse:events"
GROUP = "logpulse-workers"
KEY_LEVEL = "logpulse:stats:level"
KEY_SERVICE = "logpulse:stats:service"
KEY_STATUS = "logpulse:stats:status"
KEY_SLOW = "logpulse:slow"
KEY_TOTAL = "logpulse:stats:total"      # обработано worker
KEY_QUEUED = "logpulse:stats:queued"    # принято в очередь API
KEY_PROCESSED = "logpulse:processed"    # Set из rid, для идемпотентности

SLOW_KEEP = 100  # сколько медленных запросов хранить в Sorted Set

EVENT_FIELDS = (
    "timestamp", "level", "service", "ip", "method",
    "path", "status", "duration_ms", "rid",
)


def publish_events(r: Redis, events: list[dict]) -> int:
    """Кладёт события в Stream (XADD) и увеличивает счётчик принятых."""
    if not events:
        return 0
    maxlen = get_settings().stream_maxlen
    pipe = r.pipeline()
    for ev in events:
        fields = {k: str(ev[k]) for k in EVENT_FIELDS}
        pipe.xadd(STREAM, fields, maxlen=maxlen, approximate=True)
    pipe.incrby(KEY_QUEUED, len(events))
    pipe.execute()
    return len(events)


def event_from_fields(fields: dict) -> dict:
    """Собирает событие из полей сообщения Stream. KeyError/ValueError при порче."""
    event = {k: fields[k] for k in EVENT_FIELDS}
    event["status"] = int(event["status"])
    event["duration_ms"] = int(event["duration_ms"])
    return event


def apply_event(r: Redis, ev: dict, slow_threshold_ms: int | None = None) -> bool:
    """Обновляет статистику по событию. Возвращает False, если rid уже учтён.

    Проверка rid и все обновления выполняются в одной транзакции (WATCH/MULTI),
    поэтому повторная доставка того же сообщения не удваивает счётчики.
    """
    if slow_threshold_ms is None:
        slow_threshold_ms = get_settings().slow_threshold_ms
    rid = ev["rid"]

    def txn(pipe):
        if pipe.sismember(KEY_PROCESSED, rid):
            return False
        pipe.multi()
        pipe.sadd(KEY_PROCESSED, rid)
        pipe.hincrby(KEY_LEVEL, ev["level"], 1)
        pipe.hincrby(KEY_SERVICE, ev["service"], 1)
        pipe.hincrby(KEY_STATUS, str(ev["status"]), 1)
        pipe.incr(KEY_TOTAL)
        if ev["duration_ms"] >= slow_threshold_ms:
            pipe.zadd(KEY_SLOW, {rid: ev["duration_ms"]})
            pipe.zremrangebyrank(KEY_SLOW, 0, -(SLOW_KEEP + 1))
        return True

    return bool(r.transaction(txn, KEY_PROCESSED, value_from_callable=True))


def _to_int_dict(raw: dict) -> dict:
    return {k: int(v) for k, v in raw.items()}


def get_stats(r: Redis, top: int = 5) -> dict:
    """Читает агрегаты из Redis."""
    pipe = r.pipeline(transaction=False)
    pipe.get(KEY_QUEUED)
    pipe.get(KEY_TOTAL)
    pipe.hgetall(KEY_LEVEL)
    pipe.hgetall(KEY_SERVICE)
    pipe.hgetall(KEY_STATUS)
    pipe.zrevrange(KEY_SLOW, 0, top - 1, withscores=True)
    queued, total, levels, services, statuses, slow = pipe.execute()

    queued = int(queued or 0)
    total = int(total or 0)
    return {
        "queued_total": queued,
        "processed_total": total,
        "backlog": max(queued - total, 0),
        "by_level": dict(sorted(_to_int_dict(levels).items())),
        "by_service": dict(sorted(_to_int_dict(services).items())),
        "by_status": dict(sorted(_to_int_dict(statuses).items(), key=lambda kv: int(kv[0]))),
        "top_slow": [{"rid": rid, "duration_ms": int(score)} for rid, score in slow],
    }


def recent_events(r: Redis, limit: int) -> list[dict]:
    """Последние записи Stream, новые первыми (XREVRANGE)."""
    items = r.xrevrange(STREAM, max="+", min="-", count=limit)
    return [{"id": msg_id, **fields} for msg_id, fields in items]
