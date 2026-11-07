"""По одному тесту на каждое вспомогательное регулярное выражение."""
from app.parser import CTRL_RE, LOG_RE, PATH_RE, RID_RE, SECRET_RE, clean_line, mask_secrets


def test_main_mask_named_groups():
    m = LOG_RE.fullmatch(
        "2026-10-20T12:35:01Z WARN payment 203.0.113.7 POST /api/pay 429 301ms rid=ff44aa33"
    )
    assert m is not None
    assert m.groupdict() == {
        "timestamp": "2026-10-20T12:35:01Z",
        "level": "WARN",
        "service": "payment",
        "ip": "203.0.113.7",
        "method": "POST",
        "path": "/api/pay",
        "status": "429",
        "duration_ms": "301",
        "rid": "ff44aa33",
    }


def test_rid_regex():
    assert RID_RE.fullmatch("0a1b2c3d")
    assert not RID_RE.fullmatch("0A1B2C3D")
    assert not RID_RE.fullmatch("0a1b2c3")
    assert not RID_RE.fullmatch("0a1b2c3d4")
    assert not RID_RE.fullmatch("0a1b2c3g")


def test_path_regex():
    assert PATH_RE.fullmatch("/")
    assert PATH_RE.fullmatch("/api/orders/1042?page=2&sort=asc")
    assert not PATH_RE.fullmatch("api/orders")
    assert not PATH_RE.fullmatch("/api/<script>")
    assert not PATH_RE.fullmatch("/api/ordеrs")  # кириллическая "е" внутри


def test_secret_regex_masks_values():
    assert SECRET_RE.search("/login?password=qwerty")
    assert mask_secrets("/x?token=abc&api_key=k1&id=5") == "/x?token=***&api_key=***&id=5"
    assert mask_secrets("/x?PASSWORD=Z") == "/x?PASSWORD=***"
    assert mask_secrets("/api/orders?id=5") == "/api/orders?id=5"


def test_control_chars_regex_cleans_line():
    assert CTRL_RE.search("a\x00b")
    assert clean_line("  INFO\x00 ok\x07  ") == "INFO ok"
    assert clean_line("tab\tstays") == "tab\tstays"
