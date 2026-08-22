from __future__ import annotations

from artek_buddy.uploads import safe_filename, unique_inbox_path, user_file_blocks


def test_safe_filename_strips_paths_and_nuls() -> None:
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("a\x00b.txt") == "ab.txt"
    assert safe_filename("   ") == "file"


def test_unique_inbox_path_does_not_overwrite(tmp_path) -> None:
    first = unique_inbox_path(tmp_path, "notes.txt")
    first.write_text("one")
    second = unique_inbox_path(tmp_path, "notes.txt")
    assert second != first
    assert second.name.startswith("notes")


def test_user_file_blocks_include_text_and_file() -> None:
    blocks = user_file_blocks(
        "hello", [{"id": "art_1", "name": "a.png", "mime_type": "image/png", "size": 3}]
    )
    kinds = [block["kind"] for block in blocks]
    assert kinds == ["text", "file"]
    assert blocks[1]["artifact_id"] == "art_1"
