from __future__ import annotations

import importlib.util
import shutil
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

CLIENT_OWNER = Path(__file__).resolve().parents[2] / "client" / "owner_paths.py"


def _load_owner_paths():
    spec = importlib.util.spec_from_file_location("owner_paths_props", CLIENT_OWNER)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


owner_paths = _load_owner_paths()

bounded = settings(max_examples=40, deadline=400)
NAMES = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12)


def _home() -> Path:
    return Path(tempfile.mkdtemp())


def test_null_byte_is_rejected_without_raising(tmp_path: Path) -> None:
    for raw in ("notes.txt\x00/etc/passwd", "\x00", "ok\x00ignored"):
        path, err = owner_paths.inspect_owner_path(raw, tmp_path, must_exist=False)
        assert path is None
        assert "outside" in err


def test_dotdot_filename_cannot_escape_download_folder(tmp_path: Path) -> None:
    dest = owner_paths.unique_download_dest(tmp_path, "..")
    assert dest.parent == tmp_path
    assert dest.name not in {".", ".."}
    assert "\x00" not in dest.name


@bounded
@given(st.integers(min_value=1, max_value=12), NAMES)
def test_dotdot_chains_never_escape_home(ups: int, name: str) -> None:
    home = _home()
    try:
        raw = "/".join([".."] * ups + [name])
        path, err = owner_paths.inspect_owner_path(raw, home, must_exist=False)
        assert path is None
        assert "outside" in err
    finally:
        shutil.rmtree(home, ignore_errors=True)


@bounded
@given(NAMES)
def test_absolute_path_outside_home_never_enters(name: str) -> None:
    home = _home()
    outside = _home()
    try:
        target = outside / name
        target.write_text("x", encoding="utf-8")
        path, err = owner_paths.inspect_owner_path(str(target), home, must_exist=True)
        assert path is None
        assert "outside" in err
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)


@bounded
@given(st.integers(min_value=0, max_value=4), st.integers(min_value=1, max_value=6))
def test_more_dotdot_than_nesting_never_enters(depth: int, extra: int) -> None:
    home = _home()
    try:
        parts = [f"d{i}" for i in range(depth)] + ([".."] * (depth + extra)) + ["outside.txt"]
        path, err = owner_paths.inspect_owner_path("/".join(parts), home, must_exist=False)
        assert path is None
        assert "outside" in err
    finally:
        shutil.rmtree(home, ignore_errors=True)


@bounded
@given(st.text(max_size=64))
def test_inspect_never_raises_and_never_escapes(raw: str) -> None:
    home = _home()
    try:
        path, err = owner_paths.inspect_owner_path(raw, home, must_exist=False)
        assert isinstance(err, str)
        if path is not None:
            assert owner_paths._logical_under(path, home.resolve())
    finally:
        shutil.rmtree(home, ignore_errors=True)


@bounded
@given(st.text(max_size=40))
def test_download_dest_stays_in_folder_and_strips_nulls(name: str) -> None:
    folder = _home()
    try:
        dest = owner_paths.unique_download_dest(folder, name)
        assert dest.parent == folder
        assert "\x00" not in dest.name
        assert dest.name not in {".", ".."}
        assert owner_paths._logical_under(dest, folder.resolve())
    finally:
        shutil.rmtree(folder, ignore_errors=True)
