from __future__ import annotations

import sys
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[2] / "client"
if str(CLIENT) not in sys.path:
    sys.path.insert(0, str(CLIENT))

from clipboard_image import (
    attach_image_script,
    clipboard_text_is_file_ref,
    composer_redo_script,
    composer_undo_script,
    ctrl_edit_action,
    is_ctrl_shift_z,
    is_ctrl_v,
    is_ctrl_z,
    should_inject_clipboard_image,
)


def test_ctrl_v_is_the_paste_chord() -> None:
    assert is_ctrl_v(ord("v"), True) is True
    assert is_ctrl_v(ord("V"), True) is True
    assert is_ctrl_v(ord("м"), True) is True
    assert is_ctrl_v(0x06cd, True) is True  # Cyrillic_em
    assert is_ctrl_v(ord("v"), False) is False
    assert is_ctrl_v(ord("c"), True) is False


def test_ctrl_z_is_the_undo_chord() -> None:
    assert is_ctrl_z(ord("z"), True, False) is True
    assert is_ctrl_z(ord("я"), True, False) is True
    assert is_ctrl_z(0x06d1, True, False) is True  # Cyrillic_ya
    assert is_ctrl_z(ord("z"), True, True) is False
    assert is_ctrl_z(ord("z"), False, False) is False
    assert is_ctrl_shift_z(ord("z"), True, True) is True
    assert is_ctrl_shift_z(ord("я"), True, True) is True
    assert is_ctrl_shift_z(0x06d1, True, True) is True
    assert is_ctrl_shift_z(ord("z"), True, False) is False


def test_russian_layout_maps_standard_edit_shortcuts_by_physical_key() -> None:
    # Unicode codepoints
    assert ctrl_edit_action(ord("ф"), True, False) == "SelectAll"
    assert ctrl_edit_action(ord("с"), True, False) == "Copy"
    assert ctrl_edit_action(ord("ч"), True, False) == "Cut"
    assert ctrl_edit_action(ord("м"), True, False) == "Paste"
    assert ctrl_edit_action(ord("я"), True, False) == "Undo"
    assert ctrl_edit_action(ord("я"), True, True) == "Redo"
    assert ctrl_edit_action(ord("н"), True, False) == "Redo"
    # X11 Cyrillic keysyms from GDK keyval
    assert ctrl_edit_action(0x06c6, True, False) == "SelectAll"  # Cyrillic_ef
    assert ctrl_edit_action(0x06d3, True, False) == "Copy"  # Cyrillic_es
    assert ctrl_edit_action(0x06de, True, False) == "Cut"  # Cyrillic_che
    assert ctrl_edit_action(0x06cd, True, False) == "Paste"  # Cyrillic_em
    assert ctrl_edit_action(0x06d1, True, False) == "Undo"  # Cyrillic_ya
    assert ctrl_edit_action(0x06f1, True, False) == "Undo"  # Cyrillic_YA
    assert ctrl_edit_action(0x06d1, True, True) == "Redo"
    assert ctrl_edit_action(0x06ce, True, False) == "Redo"  # Cyrillic_en


def test_inject_screenshot_even_when_clip_has_a_file_uri() -> None:
    png = b"\x89PNG"
    assert should_inject_clipboard_image(png, "") is True
    assert should_inject_clipboard_image(png, "   ") is True
    assert should_inject_clipboard_image(png, "file:///tmp/Screenshot.png") is True
    assert should_inject_clipboard_image(png, "/home/artek/Pictures/shot.png") is True
    assert should_inject_clipboard_image(png, "copy\nfile:///tmp/Screenshot.png") is True
    assert should_inject_clipboard_image(png, "hello") is False
    assert should_inject_clipboard_image(None, "") is False
    assert clipboard_text_is_file_ref("file:///tmp/Screenshot.png") is True
    assert clipboard_text_is_file_ref("copy\nfile:///tmp/Screenshot.png") is True
    assert clipboard_text_is_file_ref("hello") is False


def test_script_calls_the_window_hook_with_png_bytes() -> None:
    script = attach_image_script(b"abc")
    assert "__artekAttachPastedImage" in script
    assert "screenshot-1.png" in script
    assert "image/png" in script
    assert "YWJj" in script
    assert "__artekComposerUndo" in composer_undo_script()
    assert "__artekComposerRedo" in composer_redo_script()
