from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parents[2] / "client" / "artek_buddy.py"


@pytest.fixture(scope="module")
def client_mod():
    spec = importlib.util.spec_from_file_location("artek_buddy_client_jail", CLIENT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_owner_path_inside_home(client_mod, tmp_path: Path) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("hello")
    resolved = client_mod.resolve_owner_path(str(notes), home=tmp_path)
    assert resolved == notes.resolve()


def test_owner_path_rejects_escape(client_mod, tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("nope")
    path, err = client_mod.inspect_owner_path(str(outside), tmp_path, must_exist=True)
    assert path is None
    assert "outside" in err
    assert client_mod._owner_path_status(err) == 403


def test_owner_path_missing(client_mod, tmp_path: Path) -> None:
    path, err = client_mod.inspect_owner_path("missing.txt", tmp_path, must_exist=True)
    assert path is None
    assert "not found" in err
    assert client_mod._owner_path_status(err) == 404


def test_unique_download_does_not_clobber(client_mod, tmp_path: Path) -> None:
    (tmp_path / "report.txt").write_text("old")
    dest = client_mod.unique_download_dest(tmp_path, "report.txt")
    assert dest.name != "report.txt"
    assert dest.name.startswith("report")
