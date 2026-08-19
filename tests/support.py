from __future__ import annotations

import os


def mask_secret(value: str | None) -> None:
    """Ask GitHub Actions to redact a minted value in public logs."""
    token = (value or "").strip()
    if not token or os.environ.get("GITHUB_ACTIONS") != "true":
        return
    print(f"::add-mask::{token}", flush=True)
