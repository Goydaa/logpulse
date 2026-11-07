from pathlib import Path

import pytest

from app.parser import LogParseError, parse_file, parse_line, parse_lines

GOOD = "2026-10-20T12:34:56Z INFO auth 192.0.2.10 POST /api/login 200 43ms rid=ab12cd34"
SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample.log"


def expect_error(line, code):
    with pytest.raises(LogParseError) as info:
        parse_line(line, 7)
    assert info.value.code == code
    assert info.value.line_number == 7
    return info.value


def test_valid_line_is_normalized():
    ev = parse_line(GOOD)
    assert ev == {
        "timestamp": "2026-10-20T12:34:56Z",
        "level": "INFO",
        "service": "auth",
        "ip": "192.0.2.10",
        "method": "POST",
        "path": "/api/login",
        "status": 200,
        "duration_ms": 43,
        "rid": "ab12cd34",
    }


def test_valid_error_line():
    ev = parse_line("2026-10-20T12:34:58Z ERROR orders 198.51.100.8 GET /api/orders 503 742ms rid=ee44cc22")
    assert ev["level"] == "ERROR" and ev["status"] == 503 and ev["duration_ms"] == 742


def test_bad_timestamp_month():
    expect_error(GOOD.replace("2026-10-20", "2026-13-20"), "bad_timestamp")


def test_bad_timestamp_without_z_does_not_match_format():
    expect_error(GOOD.replace("12:34:56Z", "12:34:56"), "bad_format")


def test_bad_ip_octet_out_of_range():
    expect_error(GOOD.replace("192.0.2.10", "192.0.2.256"), "bad_ip")


def test_unsupported_level():
    expect_error(GOOD.replace("INFO", "DEBUG"), "bad_level")


def test_unknown_service():
    expect_error(GOOD.replace(" auth ", " billing "), "bad_service")


def test_unsupported_method():
    expect_error(GOOD.replace("POST", "PATCH"), "bad_method")


@pytest.mark.parametrize("status", ["99", "600", "777", "0"])
def test_bad_status(status):
    expect_error(GOOD.replace(" 200 ", f" {status} "), "bad_status")


def test_negative_duration():
    err = expect_error(GOOD.replace("43ms", "-5ms"), "bad_duration")
    assert "отрицательная" in err.reason


def test_duration_above_limit():
    expect_error(GOOD.replace("43ms", "600001ms"), "bad_duration")


def test_duration_boundaries_are_allowed():
    assert parse_line(GOOD.replace("43ms", "0ms"))["duration_ms"] == 0
    assert parse_line(GOOD.replace("43ms", "600000ms"))["duration_ms"] == 600000


@pytest.mark.parametrize("rid", ["AB12CD34", "ab12cd3", "ab12cd345", "zz12cd34"])
def test_bad_rid(rid):
    expect_error(GOOD.replace("ab12cd34", rid), "bad_rid")


def test_path_must_start_with_slash():
    expect_error(GOOD.replace(" /api/login ", " api/login "), "bad_path")


@pytest.mark.parametrize("line", ["", "   ", "\t\n"])
def test_empty_line(line):
    expect_error(line, "empty_line")


def test_missing_field():
    expect_error("2026-10-20T12:34:56Z INFO auth 192.0.2.10 POST /api/login 200 rid=ab12cd34", "bad_format")


def test_trailing_garbage_rejected_by_fullmatch():
    expect_error(GOOD + " extra", "bad_format")


def test_secret_in_path_is_masked():
    ev = parse_line(GOOD.replace("/api/login", "/api/login?token=abc123&user=7"))
    assert "abc123" not in ev["path"]
    assert ev["path"] == "/api/login?token=***&user=7"


def test_parse_lines_mixed_batch():
    lines = [GOOD, "мусор", GOOD.replace("ab12cd34", "00000001"), "", GOOD.replace("43ms", "-1ms")]
    events, errors = parse_lines(lines)
    assert len(events) == 2
    assert [e.line_number for e in errors] == [2, 4, 5]


def test_sample_log_requirements():
    events, errors = parse_file(SAMPLE)
    total = len(events) + len(errors)
    assert total >= 40
    assert len(errors) >= 5
    assert {e["service"] for e in events} == {"auth", "orders", "payment"}
    assert {e["level"] for e in events} == {"INFO", "WARN", "ERROR"}
    assert len({e["status"] for e in events}) >= 4
    rids = [e["rid"] for e in events]
    assert len(rids) == len(set(rids))
