from __future__ import annotations

import threading
from pathlib import Path

from owner_paths import owner_downloads_dir

DESKTOP_ID = "artek-buddy"
DESKTOP_WM_CLASS = "Artek Buddy"

_WINDOW_LOCK = threading.Lock()
_GTK_WINDOWS: list[object] = []
_WINDOW_ACTIVE: bool | None = None


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


def icon_theme_path() -> Path | None:
    icon = bundled_icon_path()
    return icon.parent if icon is not None else None


def identify_desktop_app(
    *,
    glib: object | None = None,
    gdk: object | None = None,
    gtk: object | None = None,
) -> None:
    """Bind this process to the installed Artek Buddy launcher and icon."""
    if glib is None or gdk is None or gtk is None:
        try:
            from gi.repository import Gdk as gdk_mod
            from gi.repository import GLib as glib_mod
            from gi.repository import Gtk as gtk_mod
        except Exception:
            return
        glib = glib or glib_mod
        gdk = gdk or gdk_mod
        gtk = gtk or gtk_mod
    prgname = getattr(glib, "set_prgname", None)
    if callable(prgname):
        prgname(DESKTOP_ID)
    app_name = getattr(glib, "set_application_name", None)
    if callable(app_name):
        app_name(DESKTOP_WM_CLASS)
    wm_class = getattr(gdk, "set_program_class", None)
    if callable(wm_class):
        wm_class(DESKTOP_WM_CLASS)
    window_type = getattr(gtk, "Window", None)
    icon = bundled_icon_path()
    from_file = getattr(window_type, "set_default_icon_from_file", None)
    if icon is not None and callable(from_file):
        try:
            from_file(str(icon))
        except Exception:
            pass
    icon_name = getattr(window_type, "set_default_icon_name", None)
    if callable(icon_name):
        try:
            icon_name(DESKTOP_ID)
        except Exception:
            pass


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
    global _WINDOW_ACTIVE
    with _WINDOW_LOCK:
        try:
            _GTK_WINDOWS.remove(window)
        except ValueError:
            pass
        if not _GTK_WINDOWS:
            _WINDOW_ACTIVE = None


def gtk_window_active() -> bool | None:
    """GTK-thread cache. Safe to read from the loopback HTTP worker."""
    with _WINDOW_LOCK:
        if not _GTK_WINDOWS:
            return None
        return _WINDOW_ACTIVE


def remember_window_active(active: bool) -> None:
    global _WINDOW_ACTIVE
    with _WINDOW_LOCK:
        _WINDOW_ACTIVE = bool(active)


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


def window_active_script(active: bool) -> str:
    flag = "true" if active else "false"
    return (
        "if (typeof window.__artekSetWindowActive === 'function') {"
        f" window.__artekSetWindowActive({flag}); "
        "}"
    )


def _run_active_script(view: object, script: str) -> None:
    runner = getattr(view, "run_javascript", None)
    if not callable(runner):
        runner = getattr(view, "evaluate_javascript", None)
    if not callable(runner):
        return
    try:
        runner(script, None, None, None)
    except TypeError:
        try:
            runner(script)
        except Exception:
            return
    except Exception:
        return


def bind_window_active(view: object, window: object) -> None:
    def push(*_args: object) -> None:
        is_active = getattr(window, "is_active", None)
        active = bool(is_active()) if callable(is_active) else True
        remember_window_active(active)
        if active:
            _apply_urgency(False)
        _run_active_script(view, window_active_script(active))

    connect_w = getattr(window, "connect", None)
    if callable(connect_w):
        connect_w("notify::is-active", push)
        for name in ("focus-out-event", "focus-in-event"):
            try:
                connect_w(name, push)
            except Exception:
                continue
    connect_v = getattr(view, "connect", None)
    if not callable(connect_v):
        return
    for name in ("load-changed", "load-finished"):
        try:
            connect_v(name, push)
            break
        except Exception:
            continue
