"""Разбор строк журнала сервисов auth / orders / payment.

Формат строки:
    <timestamp>Z <LEVEL> <service> <ip> <METHOD> <path> <status> <N>ms rid=<8 hex>

Сначала строка целиком сопоставляется с одной основной маской (LOG_RE),
затем каждое поле проверяется отдельно: datetime, ipaddress, диапазоны чисел,
списки допустимых значений и вспомогательные регулярные выражения.
"""
import ipaddress
import re
import sys
from datetime import datetime

ALLOWED_LEVELS = ("INFO", "WARN", "ERROR")
ALLOWED_SERVICES = ("auth", "orders", "payment")
ALLOWED_METHODS = ("GET", "POST", "PUT", "DELETE")

STATUS_MIN, STATUS_MAX = 100, 599
DURATION_MIN, DURATION_MAX = 0, 600_000

# Основная маска. Уровень, сервис и метод здесь описаны шире, чем допустимые
# значения: так ошибка в них получает свою причину, а не общий отказ по формату.
LOG_RE = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"
    r" (?P<level>[A-Z]+)"
    r" (?P<service>[a-z]+)"
    r" (?P<ip>\d{1,3}(?:\.\d{1,3}){3})"
    r" (?P<method>[A-Z]+)"
    r" (?P<path>\S+)"
    r" (?P<status>\d+)"
    r" (?P<duration_ms>-?\d+)ms"
    r" rid=(?P<rid>\S+)"
)

# Вспомогательные выражения.
# 1) идентификатор запроса: ровно 8 шестнадцатеричных символов в нижнем регистре
RID_RE = re.compile(r"[0-9a-f]{8}")
# 2) путь: начинается с "/", дальше только допустимые символы URL
PATH_RE = re.compile(r"/[\w.~%:@!$&'()*+,;=?/#-]*", re.ASCII)
# 3) секреты в query-строке пути, которые маскируются перед отправкой в очередь
SECRET_RE = re.compile(
    r"(?i)\b(token|password|passwd|secret|api[_-]?key)=[^&\s]+"
)
# 4) управляющие символы, которые удаляются из строки до разбора
CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class LogParseError(ValueError):
    """Ошибка разбора: машинный код, причина и номер строки."""

    def __init__(self, code: str, reason: str, line_number: int = 1):
        self.code = code
        self.reason = reason
        self.line_number = line_number
        super().__init__(f"строка {line_number}: {reason}")


def clean_line(line: str) -> str:
    """Убирает управляющие символы и пробелы по краям."""
    return CTRL_RE.sub("", line).strip()


def mask_secrets(path: str) -> str:
    """Заменяет значения token/password/secret/api_key на ***."""
    return SECRET_RE.sub(lambda m: f"{m.group(1)}=***", path)


def parse_line(line: str, line_number: int = 1) -> dict:
    """Разбирает одну строку и возвращает нормализованный словарь.

    При любой проблеме бросает LogParseError.
    """
    text = clean_line(line)
    if not text:
        raise LogParseError("empty_line", "пустая строка", line_number)

    m = LOG_RE.fullmatch(text)
    if m is None:
        raise LogParseError(
            "bad_format",
            "строка не соответствует формату "
            "'<время>Z <уровень> <сервис> <ip> <метод> <путь> <код> <N>ms rid=<8 hex>'",
            line_number,
        )
    g = m.groupdict()

    try:
        datetime.strptime(g["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise LogParseError(
            "bad_timestamp",
            f"некорректная дата или время: {g['timestamp']}",
            line_number,
        ) from None

    if g["level"] not in ALLOWED_LEVELS:
        raise LogParseError(
            "bad_level", f"неподдерживаемый уровень: {g['level']}", line_number
        )
    if g["service"] not in ALLOWED_SERVICES:
        raise LogParseError(
            "bad_service", f"неизвестный сервис: {g['service']}", line_number
        )

    try:
        ip = str(ipaddress.IPv4Address(g["ip"]))
    except ValueError:
        raise LogParseError(
            "bad_ip", f"некорректный IPv4-адрес: {g['ip']}", line_number
        ) from None

    if g["method"] not in ALLOWED_METHODS:
        raise LogParseError(
            "bad_method", f"неподдерживаемый HTTP-метод: {g['method']}", line_number
        )

    if not PATH_RE.fullmatch(g["path"]):
        raise LogParseError(
            "bad_path",
            f"путь должен начинаться с '/' и содержать допустимые символы: {g['path']}",
            line_number,
        )

    status = int(g["status"])
    if not STATUS_MIN <= status <= STATUS_MAX:
        raise LogParseError(
            "bad_status",
            f"HTTP-код {status} вне диапазона {STATUS_MIN}-{STATUS_MAX}",
            line_number,
        )

    duration = int(g["duration_ms"])
    if duration < DURATION_MIN:
        raise LogParseError(
            "bad_duration", f"отрицательная длительность: {duration} мс", line_number
        )
    if duration > DURATION_MAX:
        raise LogParseError(
            "bad_duration",
            f"длительность {duration} мс больше допустимых {DURATION_MAX} мс",
            line_number,
        )

    if not RID_RE.fullmatch(g["rid"]):
        raise LogParseError(
            "bad_rid",
            f"rid должен состоять из 8 шестнадцатеричных символов: {g['rid']}",
            line_number,
        )

    return {
        "timestamp": g["timestamp"],
        "level": g["level"],
        "service": g["service"],
        "ip": ip,
        "method": g["method"],
        "path": mask_secrets(g["path"]),
        "status": status,
        "duration_ms": duration,
        "rid": g["rid"],
    }


def parse_lines(lines):
    """Разбирает список строк. Возвращает (события, ошибки)."""
    events, errors = [], []
    for number, line in enumerate(lines, start=1):
        try:
            events.append(parse_line(line, number))
        except LogParseError as exc:
            errors.append(exc)
    return events, errors


def parse_file(path: str):
    """Читает файл журнала и разбирает его построчно (пустые строки пропускаются)."""
    with open(path, encoding="utf-8") as fh:
        lines = [ln.rstrip("\n") for ln in fh if ln.strip()]
    return parse_lines(lines)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "data/sample.log"
    ok, bad = parse_file(target)
    print(f"{target}: корректных {len(ok)}, некорректных {len(bad)}")
    for err in bad:
        print(f"  {err}")
