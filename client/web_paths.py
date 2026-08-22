"""Serve packaged window files without leaving the web root."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

_KNOWN_TYPES = frozenset(
    {
        "application/javascript",
        "application/json",
        "application/octet-stream",
        "font/woff",
        "font/woff2",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/svg+xml",
        "image/webp",
        "text/css",
        "text/html",
        "text/javascript",
    }
)


def _inside(base: str, target: str) -> bool:
    base_r = os.path.realpath(base)
    target_r = os.path.realpath(target)
    try:
        common = os.path.commonpath([base_r, target_r])
    except ValueError:
        return False
    return common == base_r


def web_file_for_request(root: Path, url_path: str) -> Path | None:
    raw = url_path.split("?", 1)[0]
    if any(ch in raw for ch in "\x00\r\n"):
        return None
    if raw in {"", "/"}:
        raw = "/index.html"
    rel = raw.lstrip("/")
    parts = [p for p in rel.split("/") if p not in {"", "."}]
    if any(p == ".." for p in parts):
        return None
    base = os.path.realpath(root)
    target = os.path.realpath(os.path.join(base, *parts))
    if not _inside(base, target):
        return None
    if os.path.isdir(target):
        target = os.path.realpath(os.path.join(target, "index.html"))
        if not _inside(base, target):
            return None
    if os.path.isfile(target):
        return Path(target)
    fallback = os.path.realpath(os.path.join(base, "index.html"))
    if _inside(base, fallback) and os.path.isfile(fallback):
        return Path(fallback)
    return None


def safe_content_type(path: Path) -> str:
    guessed = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    cleaned = guessed.replace("\r", "").replace("\n", "")
    if cleaned not in _KNOWN_TYPES:
        return "application/octet-stream"
    return cleaned
