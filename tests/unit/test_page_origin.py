from __future__ import annotations

from starlette.requests import Request

from artek_buddy.http.page import _public_origin, _same_origin


def _request(
    *,
    origin: str | None,
    host: str,
    scheme: str = "http",
    forwarded: str | None = None,
    forwarded_host: str | None = None,
    client: str = "127.0.0.1",
) -> Request:
    headers: list[tuple[bytes, bytes]] = [(b"host", host.encode("ascii"))]
    if origin is not None:
        headers.append((b"origin", origin.encode("ascii")))
    if forwarded is not None:
        headers.append((b"x-forwarded-proto", forwarded.encode("ascii")))
    if forwarded_host is not None:
        headers.append((b"x-forwarded-host", forwarded_host.encode("ascii")))
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
            "client": (client, 50000),
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


def test_funnel_https_origin_matches_loopback_host_via_forwarded_headers() -> None:
    req = _request(
        origin="https://buddy.example",
        host="127.0.0.1:8080",
        scheme="http",
        forwarded="https",
        forwarded_host="buddy.example",
    )
    assert _same_origin(req, mutating=True) is True
    assert _public_origin(req) == "https://buddy.example"


def test_forwarded_host_does_not_admit_a_different_origin() -> None:
    req = _request(
        origin="https://evil.example",
        host="127.0.0.1:8080",
        scheme="http",
        forwarded="https",
        forwarded_host="buddy.example",
    )
    assert _same_origin(req, mutating=True) is False


def test_remote_client_cannot_spoof_funnel_forwarded_host() -> None:
    req = _request(
        origin="https://buddy.example",
        host="127.0.0.1:8080",
        scheme="http",
        forwarded="https",
        forwarded_host="buddy.example",
        client="203.0.113.10",
    )
    assert _same_origin(req, mutating=True) is False
    assert _public_origin(req) == "http://127.0.0.1:8080"
