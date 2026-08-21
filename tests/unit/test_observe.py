from __future__ import annotations

from artek_buddy.computer.observe import (
    GENERIC_TITLES,
    image_reason,
    parse_observe_output,
    shape_observe,
    should_attach_image,
)


def test_useful_title_stays_slim() -> None:
    raw = {"ok": True, "output": "GEOM 1280 800\nCURSOR X=10 Y=10\nWINDOW 7\nTITLE Inbox - Gmail"}
    shaped = shape_observe(raw, image_b64="AAA", reason=image_reason("Inbox - Gmail", False))
    assert shaped["title"] == "Inbox - Gmail"
    assert "image_png_base64" not in shaped
    assert "content" not in shaped
    assert shaped["image_reason"] == "none"


def test_empty_or_generic_title_attaches_typed_image() -> None:
    empty = parse_observe_output("GEOM 1280 800\nTITLE\n")
    assert should_attach_image(empty["title"], False) is True
    assert image_reason("", False) == "empty_title"
    assert image_reason("Chromium", False) == "generic_title"
    assert "chromium" in GENERIC_TITLES
    shaped = shape_observe(
        {"ok": True, "output": "TITLE Chromium"},
        image_b64="abc",
        reason="generic_title",
    )
    assert shaped["content"] == [{"type": "image", "mime_type": "image/png", "data": "abc"}]
    assert "image_png_base64" not in shaped


def test_include_image_attaches_even_with_good_title() -> None:
    assert image_reason("Inbox - Gmail", True) == "requested"
    shaped = shape_observe(
        {"ok": True, "output": "TITLE Inbox - Gmail"},
        image_b64="xyz",
        reason="requested",
    )
    assert shaped["content"][0]["type"] == "image"
    assert "image_png_base64" not in shaped
