from __future__ import annotations

import os
import shutil
import subprocess

from pairing import _log
from window_chrome import _apply_urgency, notify_icon_args


def _desktop_notify(title: str, body: str, urgency: str) -> None:
    _apply_urgency(True)
    if os.environ.get("ARTEK_BUDDY_NOTIFY") == "0":
        _log("notify skipped")
        return
    notify = shutil.which("notify-send")
    if not notify:
        _log("notify-send missing")
        return
    try:
        subprocess.run(
            [
                notify,
                "--app-name=Artek Buddy",
                f"--urgency={urgency}",
                "--hint=string:desktop-entry:artek-buddy",
                *notify_icon_args(),
                "--",
                title,
                body,
            ],
            check=False,
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        _log("notify-send failed")
