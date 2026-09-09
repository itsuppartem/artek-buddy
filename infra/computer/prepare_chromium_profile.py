#!/usr/bin/env python3
"""Mark the Chromium profile as a clean exit and default-allow site chrome."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Chromium content setting: 1 allow, 2 block.
ALLOW = 1
CONTENT_KEYS = (
    "geolocation",
    "notifications",
    "media_stream",
    "media_stream_mic",
    "media_stream_camera",
    "clipboard",
)


def prepare_chromium_profile(profile: Path) -> None:
    profile.mkdir(parents=True, exist_ok=True)
    default = profile / "Default"
    default.mkdir(parents=True, exist_ok=True)
    _patch_prefs(default / "Preferences")
    _patch_local_state(profile / "Local State")


def _load(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _dump(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")


def _patch_prefs(path: Path) -> None:
    data = _load(path)
    profile = data.get("profile")
    if not isinstance(profile, dict):
        profile = {}
        data["profile"] = profile
    profile["exit_type"] = "Normal"
    profile["exited_cleanly"] = True
    values = profile.get("default_content_setting_values")
    if not isinstance(values, dict):
        values = {}
        profile["default_content_setting_values"] = values
    for key in CONTENT_KEYS:
        values[key] = ALLOW
    _dump(path, data)


def _patch_local_state(path: Path) -> None:
    data = _load(path)
    data["exited_cleanly"] = True
    _dump(path, data)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: prepare_chromium_profile.py PROFILE_DIR", file=sys.stderr)
        return 2
    prepare_chromium_profile(Path(argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
