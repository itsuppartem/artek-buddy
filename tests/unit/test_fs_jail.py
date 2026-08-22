from __future__ import annotations

from pathlib import Path

from artek_buddy.fs_jail import contained_under


def test_contained_under_keeps_a_normal_bot_id(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    dest = contained_under(root, "bot_deadbeef")
    assert dest == (root / "bot_deadbeef").resolve()


def test_contained_under_rejects_parent_escape(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    assert contained_under(root, "../secret") is None
    assert contained_under(root, "bot/../../etc") is None
    assert contained_under(root, "x\ny") is None
    assert contained_under(root, "x\x00y") is None
    assert contained_under(root, ".") is None
