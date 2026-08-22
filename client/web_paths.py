"""Serve packaged window files without leaving the web root."""

from __future__ import annotations

import mimetypes
from pathlib import Path


def web_file_for_request(root: Path, url_path: str) -> Path | None:
    raw = url_path.split("?", 1)[0]
    if any(ch in raw for ch in "\x00\r\n"):
        return None
    if raw in {"", "/"}:
        raw = "/index.html"
    base = Path(root).resolve()
    target = (base / raw.lstrip("/")).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    if target.is_dir():
        target = (target / "index.html").resolve()
        try:
            target.relative_to(base)
        except ValueError:
            return None
    if target.is_file():
        return target
    fallback = (base / "index.html").resolve()
    try:
        fallback.relative_to(base)
    except ValueError:
        return None
    return fallback if fallback.is_file() else None


def safe_content_type(path: Path) -> str:
    ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    if any(ch in ctype for ch in "\r\n"):
        return "application/octet-stream"
    return ctype
