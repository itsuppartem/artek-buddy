from __future__ import annotations

import http.client
import os
import ssl
from pathlib import Path
from urllib.parse import urlsplit

from owner_paths import owner_downloads_dir, unique_download_dest
from window_chrome import _gtk_choose_save_path, _has_gtk_window

WEB_ROOTS = (
    Path("/usr/lib/artek-buddy-client/web"),
    Path(__file__).with_name("web") / "dist",
)

OWNER_FILE_MAX = 1_000_000
OWNER_OUTPUT_MAX = 200_000
OWNER_EXEC_TIMEOUT = 60
ATTACH_FILE_MAX = 25 * 1024 * 1024
ATTACH_TOTAL_MAX = 50 * 1024 * 1024
ATTACH_MAX_FILES = 10
LOCAL_JSON_MAX = 2_000_000
LOCAL_NONCE_HEADER = "X-Artek-Local-Nonce"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

save_path_chooser = None


def choose_save_path(name: str) -> Path | None:
    """Ask where to put the file. The .deb window uses a GTK Save dialog."""
    hook = save_path_chooser
    if callable(hook):
        return hook(name)
    if os.environ.get("ARTEK_SAVE_NO_DIALOG") == "1":
        return unique_download_dest(owner_downloads_dir(), name)
    if _has_gtk_window():
        return _gtk_choose_save_path(name)
    return unique_download_dest(owner_downloads_dir(), name)


def _origin_is_this_proxy(origin: str, proxy_port: int) -> bool:
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if host not in _LOOPBACK_HOSTS:
        return False
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return port == proxy_port


def proxy_origin_allowed(origin: str | None, fetch_site: str | None, proxy_port: int) -> bool:
    if (fetch_site or "").lower() == "cross-site":
        return False
    if not origin:
        return True
    return _origin_is_this_proxy(origin, proxy_port)


def local_rpc_origin_allowed(
    origin: str | None,
    fetch_site: str | None,
    proxy_port: int,
    *,
    require_origin: bool = True,
) -> bool:
    if (fetch_site or "").lower() == "cross-site":
        return False
    if not origin:
        return not require_origin
    return _origin_is_this_proxy(origin, proxy_port)


def proxy_host_allowed(host_header: str | None, proxy_port: int) -> bool:
    if not host_header:
        return False
    raw = host_header.strip()
    if raw.startswith("["):
        end = raw.find("]")
        if end < 0:
            return False
        host = raw[1:end].lower()
        rest = raw[end + 1 :]
        if rest == "":
            port = 80
        elif rest.startswith(":"):
            try:
                port = int(rest[1:])
            except ValueError:
                return False
        else:
            return False
    else:
        if raw.count(":") > 1:
            return False
        if ":" in raw:
            host, port_s = raw.rsplit(":", 1)
            try:
                port = int(port_s)
            except ValueError:
                return False
            host = host.lower()
        else:
            host = raw.lower()
            port = 80
    if host not in _LOOPBACK_HOSTS:
        return False
    return port == proxy_port


def _json_content_type(value: str | None) -> bool:
    if not value:
        return False
    return value.split(";", 1)[0].strip().lower() == "application/json"


def _host_request(
    url: str, method: str, path: str, body: bytes, headers: dict[str, str]
) -> tuple[int, bytes]:
    upstream = urlsplit(url)
    if upstream.scheme == "https":
        conn: http.client.HTTPConnection = http.client.HTTPSConnection(
            upstream.hostname or "127.0.0.1",
            upstream.port or 443,
            timeout=30,
            context=ssl.create_default_context(),
        )
    else:
        conn = http.client.HTTPConnection(
            upstream.hostname or "127.0.0.1",
            upstream.port or 80,
            timeout=30,
        )
    try:
        conn.request(method, path, body=body or None, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def web_root() -> Path:
    for path in WEB_ROOTS:
        if (path / "index.html").is_file():
            return path
    raise FileNotFoundError("web UI is missing; rebuild the package")
