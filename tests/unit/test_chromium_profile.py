from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "infra" / "computer" / "prepare_chromium_profile.py"
LAUNCHER = ROOT / "infra" / "computer" / "artek-browser"
DOCKERFILE = ROOT / "infra" / "computer" / "Dockerfile"


def test_launcher_hides_restore_bubble_and_prepares_profile() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "--hide-crash-restore-bubble" in text
    assert "--use-fake-ui-for-media-stream" in text
    assert "prepare_chromium_profile.py" in text
    assert "COPY prepare_chromium_profile.py" in DOCKERFILE.read_text(encoding="utf-8")


def test_launcher_uses_shm_and_software_rasterizer() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "--disable-dev-shm-usage" not in text
    assert "--disable-software-rasterizer" not in text


def test_dockerfile_installs_emoji_fonts() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "fonts-noto-color-emoji" in text


def test_prepare_chromium_profile_clears_crash_and_allows_site_chrome(
    tmp_path: Path,
) -> None:
    profile = tmp_path / "chromium"
    prefs = profile / "Default" / "Preferences"
    prefs.parent.mkdir(parents=True)
    prefs.write_text(
        json.dumps(
            {
                "profile": {
                    "exit_type": "Crashed",
                    "exited_cleanly": False,
                    "default_content_setting_values": {"geolocation": 2},
                }
            }
        ),
        encoding="utf-8",
    )
    local_state = profile / "Local State"
    local_state.write_text(json.dumps({"exited_cleanly": False}), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), str(profile)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr

    data = json.loads(prefs.read_text(encoding="utf-8"))
    inner = data["profile"]
    assert inner["exit_type"] == "Normal"
    assert inner["exited_cleanly"] is True
    values = inner["default_content_setting_values"]
    for key in (
        "geolocation",
        "notifications",
        "media_stream",
        "media_stream_mic",
        "media_stream_camera",
        "clipboard",
    ):
        assert values[key] == 1
    assert json.loads(local_state.read_text(encoding="utf-8"))["exited_cleanly"] is True


def test_prepare_chromium_profile_creates_missing_files(tmp_path: Path) -> None:
    profile = tmp_path / "fresh"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), str(profile)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    prefs = json.loads((profile / "Default" / "Preferences").read_text(encoding="utf-8"))
    assert prefs["profile"]["exit_type"] == "Normal"
    assert prefs["profile"]["default_content_setting_values"]["geolocation"] == 1
