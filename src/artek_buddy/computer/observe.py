from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger("artek_buddy")

GENERIC_TITLES = frozenset(
    {
        "",
        "chromium",
        "google-chrome",
        "chrome",
        "untitled",
        "desktop",
        "fluxbox",
        "xterm",
        "terminal",
        "pcmanfm",
        "files",
        "n/a",
        "(null)",
    }
)

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def parse_observe_output(output: str) -> dict[str, Any]:
    title = ""
    window_id = ""
    geom = ""
    cursor = ""
    for raw in (output or "").splitlines():
        line = raw.strip()
        if line.startswith("TITLE"):
            title = line[5:].strip()
        elif line.startswith("WINDOW"):
            window_id = line[6:].strip()
        elif line.startswith("GEOM"):
            geom = line[4:].strip()
        elif line.startswith("CURSOR"):
            cursor = line[6:].strip()
    return {
        "title": title,
        "window_id": window_id,
        "geometry": geom,
        "cursor": cursor,
    }


def is_generic_title(title: str | None) -> bool:
    return (title or "").strip().lower() in GENERIC_TITLES


def image_reason(title: str | None, include_image: bool) -> str:
    if include_image:
        return "requested"
    if not (title or "").strip():
        return "empty_title"
    if is_generic_title(title):
        return "generic_title"
    return "none"


def should_attach_image(title: str | None, include_image: bool) -> bool:
    return image_reason(title, include_image) != "none"


def shape_observe(
    raw: dict[str, Any],
    *,
    image_b64: str | None,
    reason: str,
) -> dict[str, Any]:
    parsed = parse_observe_output(str(raw.get("output") or ""))
    payload: dict[str, Any] = {
        "ok": bool(raw.get("ok", True)),
        "geometry": parsed["geometry"],
        "cursor": parsed["cursor"],
        "title": parsed["title"],
        "window_id": parsed["window_id"],
        "image_reason": reason,
    }
    if raw.get("error"):
        payload["error"] = raw["error"]
    if image_b64 and reason != "none":
        payload["content"] = [
            {"type": "image", "mime_type": "image/png", "data": image_b64},
        ]
    log_tool_result("computer_observe", payload, image=reason)
    return payload


def log_tool_result(name: str, payload: dict[str, Any], *, image: str = "none") -> None:
    try:
        size = len(json.dumps(payload, default=str))
    except Exception:
        size = 0
    log.info("tool_result name=%s bytes=%s image=%s", name, size, image)
