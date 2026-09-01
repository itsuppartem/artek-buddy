from __future__ import annotations

import os
import shutil
import subprocess
import threading

from pairing import _log
from window_chrome import _apply_urgency, bundled_icon_path, notify_icon_args

_ACTIVE_NOTES: list[object] = []
_ACTIVE_BY_TAG: dict[str, object] = {}
_NOTIFY_LOCK = threading.RLock()

_URGENCY_ATTR = {
    "low": "LOW",
    "normal": "NORMAL",
    "critical": "CRITICAL",
}


def _libnotify_api() -> object | None:
    try:
        import gi

        gi.require_version("Notify", "0.7")
        from gi.repository import Notify
    except (ImportError, ValueError):
        return None
    return Notify


def _desktop_notify(title: str, body: str, urgency: str, tag: str = "") -> None:
    _apply_urgency(True)
    if os.environ.get("ARTEK_BUDDY_NOTIFY") == "0":
        _log("notify skipped")
        return
    if _show_libnotify(title, body, urgency, tag):
        return
    _show_notify_send(title, body, urgency)


def _desktop_dismiss(tag: str) -> bool:
    if not tag:
        return False
    with _NOTIFY_LOCK:
        previous = _ACTIVE_BY_TAG.pop(tag, None)
        if previous is None:
            return False
        closer = getattr(previous, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass
        try:
            _ACTIVE_NOTES.remove(previous)
        except ValueError:
            pass
        return True


def _show_libnotify(title: str, body: str, urgency: str, tag: str = "") -> bool:
    api = _libnotify_api()
    if api is None:
        return False
    try:
        needs_init = not api.is_initted() if hasattr(api, "is_initted") else True
        if needs_init and not api.init("Artek Buddy"):
            return False
        with _NOTIFY_LOCK:
            icon = bundled_icon_path()
            icon_name = str(icon) if icon is not None else "artek-buddy"
            note = _ACTIVE_BY_TAG.get(tag) if tag else None
            if note is not None:
                updater = getattr(note, "update", None)
                if callable(updater):
                    updater(title, body, icon_name)
                else:
                    _desktop_dismiss(tag)
                    note = None
            if note is None:
                note = api.Notification.new(title, body, icon_name)
                _ACTIVE_NOTES.append(note)
                if tag:
                    _ACTIVE_BY_TAG[tag] = note
            urgency_enum = getattr(api, "Urgency", None)
            level = getattr(urgency_enum, _URGENCY_ATTR.get(urgency, "NORMAL"), None)
            setter = getattr(note, "set_urgency", None)
            if callable(setter) and level is not None:
                setter(level)
            hint = getattr(note, "set_hint_string", None)
            if callable(hint):
                hint("desktop-entry", "artek-buddy")
            note.show()
            if len(_ACTIVE_NOTES) > 20:
                extra = _ACTIVE_NOTES[:-12]
                del _ACTIVE_NOTES[:-12]
                for stale in extra:
                    for key, held in list(_ACTIVE_BY_TAG.items()):
                        if held is stale:
                            _ACTIVE_BY_TAG.pop(key, None)
        return True
    except Exception as exc:
        _log(f"libnotify failed: {type(exc).__name__}")
        return False


def _show_notify_send(title: str, body: str, urgency: str) -> None:
    notify = shutil.which("notify-send")
    if not notify:
        _log("notify-send missing")
        return
    try:
        # Omit desktop-entry: GNOME looks up artek-buddy.desktop, then
        # destroys that source when notify-send leaves the bus.
        subprocess.run(
            [
                notify,
                "--app-name=Artek Buddy",
                f"--urgency={urgency}",
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
