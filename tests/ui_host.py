"""Guards so Playwright never talks to the live compose host."""

from __future__ import annotations

from urllib.parse import urlparse

from tests.pgutil import is_live_compose_url


def is_live_http_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return True
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return port == 8080


def refuse_live_stack(database_url: str, host_url: str) -> None:
    if is_live_compose_url(database_url):
        raise SystemExit("run_ui: refusing the live compose database")
    if is_live_http_url(host_url):
        raise SystemExit("run_ui: refusing the live host HTTP port")
