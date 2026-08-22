from __future__ import annotations

import threading
from pathlib import Path

from owner_paths import owner_downloads_dir

_WINDOW_LOCK = threading.Lock()
_GTK_WINDOWS: list[object] = []


def _has_gtk_window() -> bool:
    with _WINDOW_LOCK:
        return bool(_GTK_WINDOWS)


def _gtk_parent() -> object | None:
    with _WINDOW_LOCK:
        return _GTK_WINDOWS[0] if _GTK_WINDOWS else None


def _gtk_choose_save_path(name: str) -> Path | None:
    from gi.repository import GLib, Gtk

    done = threading.Event()
    chosen: list[Path | None] = [None]
    safe = Path(str(name or "file").replace("\x00", "")).name.strip() or "file"

    def show() -> bool:
        dialog = None
        try:
            dialog = Gtk.FileChooserNative.new(
                "Save file",
                _gtk_parent(),
                Gtk.FileChooserAction.SAVE,
                "Save",
                "Cancel",
            )
            dialog.set_current_name(safe)
            try:
                dialog.set_current_folder(str(owner_downloads_dir()))
            except Exception:
                pass
            setter = getattr(dialog, "set_do_overwrite_confirmation", None)
            if callable(setter):
                setter(True)
            response = dialog.run()
            if response == Gtk.ResponseType.ACCEPT:
                filename = dialog.get_filename()
                if filename:
                    chosen[0] = Path(filename)
        except Exception:
            chosen[0] = None
        finally:
            if dialog is not None:
                dialog.destroy()
            done.set()
        return False

    GLib.idle_add(show)
    if not done.wait(timeout=600):
        return None
    return chosen[0]


def _icon_candidates() -> list[Path]:
    here = Path(__file__).resolve().parent
    return [
        Path("/usr/share/icons/hicolor/256x256/apps/artek-buddy.png"),
        Path("/usr/lib/artek-buddy-client/app-icon.png"),
        here / "assets" / "app-icon.png",
        here / "assets" / "hicolor" / "256x256" / "apps" / "artek-buddy.png",
    ]


def bundled_icon_path() -> Path | None:
    for path in _icon_candidates():
        if path.is_file():
            return path
    return None


def notify_icon_args() -> list[str]:
    icon = bundled_icon_path()
    if icon is not None:
        return [f"--icon={icon}"]
    return ["--icon=artek-buddy"]


def apply_window_icon(window: object) -> None:
    icon = bundled_icon_path()
    setter = getattr(window, "set_icon_from_file", None)
    if icon is not None and callable(setter):
        try:
            setter(str(icon))
            return
        except Exception:
            pass
    name_setter = getattr(window, "set_icon_name", None)
    if callable(name_setter):
        try:
            name_setter("artek-buddy")
        except Exception:
            pass


def _notify_text(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _register_window(window: object) -> None:
    with _WINDOW_LOCK:
        if window not in _GTK_WINDOWS:
            _GTK_WINDOWS.append(window)


def _unregister_window(window: object) -> None:
    with _WINDOW_LOCK:
        try:
            _GTK_WINDOWS.remove(window)
        except ValueError:
            pass


def _apply_urgency(urgent: bool) -> None:
    def go() -> bool:
        with _WINDOW_LOCK:
            windows = list(_GTK_WINDOWS)
        for window in windows:
            setter = getattr(window, "set_urgency_hint", None)
            if setter is None:
                continue
            try:
                setter(bool(urgent))
            except Exception:
                pass
        return False

    try:
        from gi.repository import GLib

        GLib.idle_add(go)
    except Exception:
        go()


def _on_focus_in(*_args: object) -> bool:
    _apply_urgency(False)
    return False


def _on_gtk_active(window: object, *_args: object) -> None:
    is_active = getattr(window, "is_active", None)
    if callable(is_active) and is_active():
        _apply_urgency(False)
