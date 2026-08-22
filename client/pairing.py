#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

_NOVNC_LOG = re.compile(r"/novnc/\S+")
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _redact_client_log(message: str) -> str:
    return _NOVNC_LOG.sub("/novnc/[redacted]", message)


def pairing_url_allowed(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    try:
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return False
    if not host:
        return False
    if port is not None and not (1 <= port <= 65535):
        return False
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    if host.endswith(".ts.net"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_private or ip in _CGNAT)


def _log(message: str) -> None:
    text = _redact_client_log(message.rstrip())
    try:
        path = Path.home() / ".config" / "artek-buddy" / "client.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        existed = path.exists()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")
        if not existed or path.stat().st_mode & 0o077:
            path.chmod(0o600)
    except OSError:
        pass
    sys.stderr.write(text + "\n")


def _config_dir() -> Path:
    return Path.home() / ".config" / "artek-buddy"


def _load_url() -> str:
    candidates = [
        _config_dir() / "url",
        Path("/usr/lib/artek-buddy-client/url"),
        Path(__file__).with_name("url"),
    ]
    for path in candidates:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value.rstrip("/")
    return os.environ.get("ARTEK_BUDDY_URL", "http://127.0.0.1:8080").rstrip("/")


def _load_token() -> str:
    if os.environ.get("ARTEK_BUDDY_UNPAIRED") == "1":
        return ""
    try:
        value = (_config_dir() / "token").read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    if value:
        return value
    for path in (
        Path("/usr/lib/artek-buddy-client/token"),
        Path(__file__).with_name("token"),
    ):
        try:
            leftover = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if leftover:
            return leftover
    return ""


def _write_text(path: Path, value: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.strip() + "\n", encoding="utf-8")
    path.chmod(mode)
