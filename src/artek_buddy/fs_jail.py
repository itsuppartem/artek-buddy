"""Keep filesystem joins inside a resolved root."""

from __future__ import annotations

from pathlib import Path


def contained_under(root: Path, relative: str) -> Path | None:
    """Return root/relative only when resolve() stays strictly inside root."""
    if any(ch in relative for ch in "\x00\r\n"):
        return None
    base = Path(root).resolve()
    target = (base / relative).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    if target == base:
        return None
    return target
