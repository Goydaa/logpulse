"""Worker: читает события из Redis Stream через consumer group."""
import logging
import signal
import threading

from redis import Redis
from redis.exceptions import RedisError, ResponseError

from app import store
from app.config import get_settings
from app.redis_client import create_redis

log = logging.getLogger("logpulse.worker")


class Worker:
    def __init__(self, r: Redis, consumer: str = "worker-1", batch_size: int = 10):
        self.r = r
        self.consumer = consumer
        self.batch_size = batch_size

    def ensure_group(self) -> None:
        try:
            self.r.xgroup_create(store.STREAM, store.GROUP, id="0", mkstream=True)
            log.info("создана группа %s", store.GROUP)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def process_batch(self, start_id: str = ">", block_ms: int | None = None) -> int:
        """Читает и обрабатывает пачку сообщений. Возвращает число прочитанных.

        start_id=">"  новые сообщения;
        start_id="0"  сообщения этого consumer'а, которые прочитаны, но не подтверждены.
        """
        resp = self.r.xreadgroup(
            store.GROUP,
            self.consumer,
            {store.STREAM: start_id},
            count=self.batch_size,
            block=block_ms,
        )
        if not resp:
            return 0
        count = 0
        for _stream, messages in resp:
            for msg_id, fields in messages:
                self.handle(msg_id, fields)
                count += 1
        return count

    def handle(self, msg_id: str, fields: dict | None) -> None:
        try:
            event = store.event_from_fields(fields or {})
        except (KeyError, ValueError, TypeError):
            # повреждённое сообщение не обработать никогда: подтверждаем, иначе оно зациклится
            log.warning("сообщение %s повреждено, пропущено", msg_id)
            self.r.xack(store.STREAM, store.GROUP, msg_id)
            return

        applied = store.apply_event(self.r, event, get_settings().slow_threshold_ms)
        if not applied:
            log.info("rid=%s уже учтён, повторная доставка пропущена", event["rid"])
        # XACK только после успешного обновления статистики
        self.r.xack(store.STREAM, store.GROUP, msg_id)

    def recover_pending(self) -> int:
        """После перезапуска дочитывает неподтверждённые сообщения."""
        total = 0
        while True:
            n = self.process_batch("0")
            if n == 0:
                return total
            total += n

    def run(self, stop: threading.Event, block_ms: int = 2000) -> None:
        delay = 1.0
        while not stop.is_set():
            try:
                self.ensure_group()
                recovered = self.recover_pending()
                if recovered:
                    log.info("дочитано неподтверждённых сообщений: %d", recovered)
                log.info("worker запущен, consumer=%s", self.consumer)
                delay = 1.0
                while not stop.is_set():
                    self.process_batch(">", block_ms=block_ms)
            except RedisError as exc:
                log.error("Redis недоступен (%s), повтор через %.0f с", exc, delay)
                stop.wait(delay)
                delay = min(delay * 2, 10.0)
            except Exception:
                log.exception("непредвиденная ошибка worker, повтор через %.0f с", delay)
                stop.wait(delay)
                delay = min(delay * 2, 10.0)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    r = create_redis(settings, socket_timeout=settings.worker_block_ms / 1000 + 3)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    log.info("подключение к Redis %s:%s", settings.redis_host, settings.redis_port)
    Worker(r, consumer=settings.worker_consumer).run(stop, block_ms=settings.worker_block_ms)
    log.info("worker остановлен")


if __name__ == "__main__":
    main()
