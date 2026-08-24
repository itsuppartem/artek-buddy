from __future__ import annotations

import sys
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[2] / "client"
if str(CLIENT) not in sys.path:
    sys.path.insert(0, str(CLIENT))

from clipboard_image import (
    attach_image_script,
    is_ctrl_v,
    should_inject_clipboard_image,
)


def test_ctrl_v_is_the_paste_chord() -> None:
    assert is_ctrl_v(ord("v"), True) is True
    assert is_ctrl_v(ord("V"), True) is True
    assert is_ctrl_v(ord("v"), False) is False
    assert is_ctrl_v(ord("c"), True) is False


def test_inject_only_when_clipboard_is_an_image_without_text() -> None:
    png = b"\x89PNG"
    assert should_inject_clipboard_image(png, "") is True
    assert should_inject_clipboard_image(png, "   ") is True
    assert should_inject_clipboard_image(png, "hello") is False
    assert should_inject_clipboard_image(None, "") is False


def test_script_calls_the_window_hook_with_png_bytes() -> None:
    script = attach_image_script(b"abc")
    assert "__artekAttachPastedImage" in script
    assert "screenshot-1.png" in script
    assert "image/png" in script
    assert "YWJj" in script
