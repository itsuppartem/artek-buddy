from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TTL_MS = 60 * 60 * 1000
PATH_RE = re.compile(
    r"^/novnc/([A-Za-z0-9_-]+)/(\d+)/(view|control)/(\d+)\.([A-Za-z0-9_-]{43})(/[^?]*)?(\?.*)?$"
)


@dataclass(frozen=True)
class NovncTarget:
    hostname: str
    port: int
    path: str
    interactive: bool


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(secret: str, hostname: str, port: int, policy: str, expires_at: int) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{hostname}:{port}:{policy}:{expires_at}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64url(digest)[:43]


def is_allowed_host(hostname: str) -> bool:
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return True
    if re.fullmatch(r"10(?:\.\d{1,3}){3}", hostname):
        return True
    if re.fullmatch(r"192\.168(?:\.\d{1,3}){2}", hostname):
        return True
    if re.fullmatch(r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}", hostname):
        return True
    return bool(re.fullmatch(r"artek-bot-[A-Za-z0-9_.-]+", hostname))


def mint_novnc_url(
    secret: str,
    hostname: str,
    port: int,
    *,
    interactive: bool = False,
    path: str = "/embed.html",
    now_ms: int | None = None,
) -> str:
    if not is_allowed_host(hostname):
        raise ValueError("host is not allowed")
    if port < 1024 or port > 65535:
        raise ValueError("port is not allowed")
    expires = (now_ms if now_ms is not None else int(time.time() * 1000)) + TTL_MS
    policy = "control" if interactive else "view"
    signature = _sign(secret, hostname, port, policy, expires)
    host_token = _b64url(hostname.encode("utf-8"))
    suffix = path if path.startswith("/") else f"/{path}"
    query = "view_only=false" if interactive else "view_only=true"
    if "?" in suffix:
        suffix = suffix.split("?", 1)[0]
    return f"/novnc/{host_token}/{port}/{policy}/{expires}.{signature}{suffix}?{query}"


def screen_policy_path(requested_path: str, interactive: bool) -> str:
    parsed = urlparse(requested_path if "://" in requested_path else f"http://screen.invalid{requested_path}")
    if parsed.path == "/embed.html" or parsed.path.endswith("/embed.html"):
        return f"{parsed.path}?view_only={'false' if interactive else 'true'}"
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "view_only" in query:
        query["view_only"] = "false" if interactive else "true"
        return urlunparse(("", "", parsed.path, "", urlencode(query), ""))
    return parsed.path or "/"


def resolve_novnc_target(url: str, secret: str, now_ms: int | None = None) -> NovncTarget | None:
    match = PATH_RE.match(url or "")
    if not match:
        return None
    hostname = _b64url_decode(match.group(1)).decode("utf-8")
    port = int(match.group(2))
    policy = match.group(3)
    expires_at = int(match.group(4))
    signature = match.group(5)
    requested = f"{match.group(6) or '/'}{match.group(7) or ''}"
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    if not is_allowed_host(hostname):
        return None
    if port < 1024 or port > 65535 or expires_at < now:
        return None
    expected = _sign(secret, hostname, port, policy, expires_at)
    if not hmac.compare_digest(signature, expected):
        return None
    interactive = policy == "control"
    return NovncTarget(
        hostname=hostname,
        port=port,
        path=screen_policy_path(requested, interactive),
        interactive=interactive,
    )


def embeddable_screen_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("/novnc/"):
        return url
    return None
