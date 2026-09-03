from __future__ import annotations

from starlette.requests import Request

from artek_buddy.http.page import _same_origin


def _request(
    *,
    origin: str | None,
    host: str,
    scheme: str = "http",
    forwarded: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = [(b"host", host.encode("ascii"))]
    if origin is not None:
        headers.append((b"origin", origin.encode("ascii")))
    if forwarded is not None:
        headers.append((b"x-forwarded-proto", forwarded.encode("ascii")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": scheme,
            "path": "/local/status",
            "raw_path": b"/local/status",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }
    )


def test_missing_origin_is_allowed_only_when_not_mutating() -> None:
    req = _request(origin=None, host="pi:8080")
    assert _same_origin(req, mutating=False) is True
    assert _same_origin(req, mutating=True) is False


def test_https_origin_does_not_match_http_host() -> None:
    req = _request(origin="https://pi:8080", host="pi:8080", scheme="http")
    assert _same_origin(req, mutating=True) is False


def test_http_origin_does_not_match_https_forwarded_host() -> None:
    req = _request(
        origin="http://pi:8080",
        host="pi:8080",
        scheme="http",
        forwarded="https",
    )
    assert _same_origin(req, mutating=True) is False


def test_alternate_port_does_not_match() -> None:
    req = _request(origin="http://pi:9", host="pi:8080", scheme="http")
    assert _same_origin(req, mutating=True) is False


def test_default_https_port_matches_host_without_port() -> None:
    req = _request(origin="https://pi", host="pi", scheme="https")
    assert _same_origin(req, mutating=True) is True


def test_matching_scheme_host_and_port_still_pairs() -> None:
    req = _request(origin="http://pi:8080", host="pi:8080", scheme="http")
    assert _same_origin(req, mutating=True) is True
