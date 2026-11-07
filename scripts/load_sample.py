"""Отправляет data/sample.log в POST /ingest пакетами до 100 строк.

Запуск на хосте:        python scripts/load_sample.py
Запуск в контейнере:    docker compose exec api python scripts/load_sample.py
Другой адрес API:       python scripts/load_sample.py http://127.0.0.1:8000
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BATCH = 100
SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample.log"


def post(url: str, lines: list[str]) -> dict:
    req = urllib.request.Request(
        url + "/ingest",
        data=json.dumps({"lines": lines}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    lines = [ln.rstrip("\n") for ln in SAMPLE.open(encoding="utf-8") if ln.strip()]
    accepted = rejected = 0
    for start in range(0, len(lines), BATCH):
        try:
            result = post(url, lines[start:start + BATCH])
        except urllib.error.URLError as exc:
            print(f"не удалось отправить пакет: {exc}")
            return 1
        accepted += result["accepted"]
        rejected += result["rejected"]
        for err in result["errors"]:
            number = start + err["line_number"]
            print(f"  строка {number}: {err['reason']}")
    print(f"всего строк: {len(lines)}, принято: {accepted}, отклонено: {rejected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
