"""Read a screenshot from the GTK clipboard and hand it to the window."""

from __future__ import annotations

import base64


def is_ctrl_v(keyval: int, ctrl: bool) -> bool:
    return bool(ctrl) and int(keyval) in {ord("v"), ord("V"), 118, 86}


def should_inject_clipboard_image(png: bytes | None, text: str | None) -> bool:
    return bool(png) and not (text or "").strip()


def attach_image_script(png: bytes) -> str:
    payload = base64.b64encode(png).decode("ascii")
    return (
        "if (typeof window.__artekAttachPastedImage === 'function') {"
        f" window.__artekAttachPastedImage({payload!r}, 'image/png', 'screenshot-1.png'); "
        "}"
    )


def read_gtk3_clipboard() -> tuple[bytes | None, str]:
    from gi.repository import Gdk, Gtk

    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    text = clipboard.wait_for_text() or ""
    image = clipboard.wait_for_image()
    if image is None:
        return None, text
    ok, buf = image.save_to_bufferv("png", [], [])
    if not ok or not buf:
        return None, text
    return bytes(buf), text


def bind_webkit_paste(view: object) -> None:
    try:
        from gi.repository import Gdk
    except Exception:
        return

    control = int(getattr(getattr(Gdk, "ModifierType", None), "CONTROL_MASK", 4))

    def on_key(_widget: object, event: object) -> bool:
        state = int(getattr(event, "state", 0) or 0)
        keyval = int(getattr(event, "keyval", 0) or 0)
        if not is_ctrl_v(keyval, bool(state & control)):
            return False
        try:
            png, text = read_gtk3_clipboard()
        except Exception:
            return False
        if not should_inject_clipboard_image(png, text) or png is None:
            return False
        script = attach_image_script(png)
        runner = getattr(view, "run_javascript", None)
        if not callable(runner):
            return False
        try:
            runner(script, None, None, None)
        except TypeError:
            try:
                runner(script)
            except Exception:
                return False
        except Exception:
            return False
        return True

    connect = getattr(view, "connect", None)
    if callable(connect):
        try:
            connect("key-press-event", on_key)
        except Exception:
            pass
    try:
        from gi.repository import Gtk

        controller = Gtk.EventControllerKey()
        controller.connect(
            "key-pressed",
            lambda _c, keyval, _code, state: on_key(
                view, type("E", (), {"keyval": keyval, "state": state})()
            ),
        )
        add = getattr(view, "add_controller", None)
        if callable(add):
            add(controller)
    except Exception:
        pass
