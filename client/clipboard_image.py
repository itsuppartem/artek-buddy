"""Read a screenshot from the GTK clipboard and hand it to the window."""

from __future__ import annotations

import base64
import re

_FILE_REF = re.compile(
    r"(?is)^(file:/|https?://\S+\.(?:png|jpe?g|webp|gif)(?:\s|$)|~?/[\w./-]+\.(?:png|jpe?g|webp|gif)\s*$)"
)
_RU_PHYSICAL_KEYS = {
    "ф": "a",
    "с": "c",
    "м": "v",
    "ч": "x",
    "н": "y",
    "я": "z",
}

_KEYVAL_MAP: dict[int, str] = {
    # X11 Cyrillic keysyms -> physical Latin equivalent
    0x06c6: "a",  # Cyrillic_ef
    0x06e6: "a",  # Cyrillic_EF
    0x06d3: "c",  # Cyrillic_es
    0x06f3: "c",  # Cyrillic_ES
    0x06cd: "v",  # Cyrillic_em
    0x06ed: "v",  # Cyrillic_EM
    0x06de: "x",  # Cyrillic_che
    0x06fe: "x",  # Cyrillic_CHE
    0x06ce: "y",  # Cyrillic_en
    0x06ee: "y",  # Cyrillic_EN
    0x06d1: "z",  # Cyrillic_ya
    0x06f1: "z",  # Cyrillic_YA
    # Standard Latin keysyms / ASCII
    ord("a"): "a",
    ord("A"): "a",
    ord("c"): "c",
    ord("C"): "c",
    ord("v"): "v",
    ord("V"): "v",
    ord("x"): "x",
    ord("X"): "x",
    ord("y"): "y",
    ord("Y"): "y",
    ord("z"): "z",
    ord("Z"): "z",
    # Unicode Cyrillic codepoints
    ord("ф"): "a",
    ord("Ф"): "a",
    ord("с"): "c",
    ord("С"): "c",
    ord("м"): "v",
    ord("М"): "v",
    ord("ч"): "x",
    ord("Ч"): "x",
    ord("н"): "y",
    ord("Н"): "y",
    ord("я"): "z",
    ord("Я"): "z",
}


def ctrl_edit_action(keyval: int, ctrl: bool, shift: bool) -> str | None:
    if not ctrl:
        return None
    key = _KEYVAL_MAP.get(int(keyval))
    if not key:
        try:
            ch = chr(int(keyval)).lower()
            key = _RU_PHYSICAL_KEYS.get(ch, ch)
        except (OverflowError, ValueError):
            return None
    actions = {"a": "SelectAll", "c": "Copy", "v": "Paste", "x": "Cut"}
    if key == "z":
        return "Redo" if shift else "Undo"
    if key == "y" and not shift:
        return "Redo"
    return actions.get(key)


def is_ctrl_v(keyval: int, ctrl: bool) -> bool:
    return ctrl_edit_action(keyval, ctrl, False) == "Paste"


def is_ctrl_z(keyval: int, ctrl: bool, shift: bool) -> bool:
    return ctrl_edit_action(keyval, ctrl, shift) == "Undo"


def is_ctrl_shift_z(keyval: int, ctrl: bool, shift: bool) -> bool:
    return ctrl_edit_action(keyval, ctrl, shift) == "Redo"


_GNOME_CLIP_ACTIONS = {"copy", "cut", "link"}


def clipboard_text_is_file_ref(text: str | None) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if "file:" in raw.lower():
        return True
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return False
    if lines[0].lower() in _GNOME_CLIP_ACTIONS and len(lines) > 1:
        return clipboard_text_is_file_ref("\n".join(lines[1:]))
    return bool(_FILE_REF.match(lines[0]))


def should_inject_clipboard_image(png: bytes | None, text: str | None) -> bool:
    if not png:
        return False
    raw = (text or "").strip()
    if not raw:
        return True
    return clipboard_text_is_file_ref(raw)


def attach_image_script(png: bytes) -> str:
    payload = base64.b64encode(png).decode("ascii")
    return (
        "if (typeof window.__artekAttachPastedImage === 'function') {"
        f" window.__artekAttachPastedImage({payload!r}, 'image/png', 'screenshot-1.png'); "
        "}"
    )


def composer_undo_script() -> str:
    return "if (typeof window.__artekComposerUndo === 'function') { window.__artekComposerUndo(); }"


def composer_redo_script() -> str:
    return "if (typeof window.__artekComposerRedo === 'function') { window.__artekComposerRedo(); }"


def _pixbuf_png(image: object) -> bytes | None:
    ok, buf = image.save_to_bufferv("png", [], [])  # type: ignore[attr-defined]
    if not ok or not buf:
        return None
    return bytes(buf)


def _selection_png(clipboard: object, name: str) -> bytes | None:
    try:
        from gi.repository import Gdk
    except Exception:
        return None
    intern = getattr(Gdk, "Atom", None)
    if intern is None or not hasattr(intern, "intern"):
        return None
    atom = intern.intern(name, False)
    getter = getattr(clipboard, "wait_for_contents", None)
    if not callable(getter):
        return None
    payload = getter(atom)
    if payload is None:
        return None
    data = getattr(payload, "get_data", None)
    if not callable(data):
        return None
    raw = data()
    return bytes(raw) if raw else None


def read_gtk3_clipboard() -> tuple[bytes | None, str]:
    from gi.repository import Gdk, Gtk

    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    text = clipboard.wait_for_text() or ""
    image = clipboard.wait_for_image()
    png = _pixbuf_png(image) if image is not None else None
    if png is None:
        png = _selection_png(clipboard, "image/png") or _selection_png(clipboard, "image/jpeg")
    return png, text


def _run_script(view: object, script: str) -> bool:
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


def _run_editing_command(view: object, command: str) -> bool:
    execute = getattr(view, "execute_editing_command", None)
    if not callable(execute):
        return False
    try:
        execute(command)
    except Exception:
        return False
    return True


def bind_webkit_paste(view: object) -> None:
    try:
        from gi.repository import Gdk
    except Exception:
        return

    control = int(getattr(getattr(Gdk, "ModifierType", None), "CONTROL_MASK", 4))
    shift = int(getattr(getattr(Gdk, "ModifierType", None), "SHIFT_MASK", 1))

    def on_key(_widget: object, event: object) -> bool:
        state = int(getattr(event, "state", 0) or 0)
        keyval = int(getattr(event, "keyval", 0) or 0)
        ctrl = bool(state & control)
        shifted = bool(state & shift)
        action = ctrl_edit_action(keyval, ctrl, shifted)
        if action == "Undo":
            return _run_script(view, composer_undo_script())
        if action == "Redo":
            return _run_script(view, composer_redo_script())
        if action is None:
            return False
        if action == "Paste":
            try:
                png, text = read_gtk3_clipboard()
            except Exception:
                png, text = None, ""
            if should_inject_clipboard_image(png, text) and png is not None:
                return _run_script(view, attach_image_script(png))
        return _run_editing_command(view, action)

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
