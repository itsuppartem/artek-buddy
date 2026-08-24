from __future__ import annotations

import traceback

from pairing import _log
from window_chrome import (
    _on_focus_in,
    _on_gtk_active,
    _register_window,
    _unregister_window,
    apply_window_icon,
)


def _open_webkit2(local_url: str) -> bool:
    import gi

    gi.require_version("Gtk", "3.0")
    loaded = None
    for version in ("4.1", "4.0"):
        try:
            gi.require_version("WebKit2", version)
            loaded = version
            break
        except ValueError:
            continue
    if loaded is None:
        raise RuntimeError("WebKit2 typelib not found")
    from gi.repository import Gtk, WebKit2

    window = Gtk.Window(title="Artek Buddy")
    window.set_default_size(1440, 900)
    apply_window_icon(window)
    window.connect("destroy", lambda *_args: (_unregister_window(window), Gtk.main_quit()))
    window.connect("focus-in-event", _on_focus_in)
    view = WebKit2.WebView()
    try:
        from clipboard_image import bind_webkit_paste

        bind_webkit_paste(view)
    except Exception:
        pass
    view.load_uri(local_url)
    window.add(view)
    _register_window(window)
    window.show_all()
    Gtk.main()
    return True


def _open_webkit6(local_url: str) -> bool:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("WebKit", "6.0")
    from gi.repository import Gtk, WebKit

    def on_activate(app: Gtk.Application) -> None:
        window = Gtk.ApplicationWindow(application=app, title="Artek Buddy")
        window.set_default_size(1440, 900)
        apply_window_icon(window)
        try:
            Gtk.Window.set_default_icon_name("artek-buddy")
        except Exception:
            pass
        window.connect("notify::is-active", _on_gtk_active)
        window.connect("destroy", lambda *_args: _unregister_window(window))
        view = WebKit.WebView()
        try:
            from clipboard_image import bind_webkit_paste

            bind_webkit_paste(view)
        except Exception:
            pass
        view.load_uri(local_url)
        window.set_child(view)
        _register_window(window)
        window.present()

    app = Gtk.Application(application_id="local.artek.buddy")
    app.connect("activate", on_activate)
    app.run(None)
    return True


def open_window(local_url: str) -> bool:
    try:
        return _open_webkit2(local_url)
    except Exception:
        _log("webkit2 window failed:\n" + traceback.format_exc())
    try:
        return _open_webkit6(local_url)
    except Exception:
        _log("webkit6 window failed:\n" + traceback.format_exc())
    return False
