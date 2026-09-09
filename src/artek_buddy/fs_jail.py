"""Keep filesystem joins inside a resolved root."""

from __future__ import annotations

import os
from pathlib import Path


def contained_under(root: Path, relative: str) -> Path | None:
    """Return root/relative only when the normalized path stays strictly inside root.

    One path segment. ``normpath`` plus ``startswith(base + sep)`` is the
    sanitizer CodeQL models for ``py/path-injection``; ``Path.resolve`` is not.
    """
    if not relative or any(ch in relative for ch in "\x00\r\n/\\"):
        return None
    if relative in {".", ".."}:
        return None
    base = os.path.abspath(str(root))
    # codeql[py/path-injection]
    target = os.path.normpath(os.path.join(base, relative))  # lgtm[py/path-injection]
    if target == base or not target.startswith(base + os.sep):
        return None
    real_base = os.path.realpath(base)
    real_target = os.path.realpath(target)
    if real_target == real_base or not real_target.startswith(real_base + os.sep):
        return None
    return Path(real_target)
