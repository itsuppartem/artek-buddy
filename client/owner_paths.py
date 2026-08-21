from __future__ import annotations

import os
from pathlib import Path

_FOLDER_ALIASES = {
    "downloads": ("Downloads", "Загрузки"),
    "загрузки": ("Downloads", "Загрузки"),
    "desktop": ("Desktop", "Рабочий стол"),
    "документы": ("Documents", "Документы"),
    "documents": ("Documents", "Документы"),
    "pictures": ("Pictures", "Изображения", "Картинки"),
    "изображения": ("Pictures", "Изображения", "Картинки"),
    "music": ("Music", "Музыка"),
    "музыка": ("Music", "Музыка"),
    "videos": ("Videos", "Видео"),
    "видео": ("Videos", "Видео"),
}


def _owner_home(home: Path | None) -> Path:
    return (home or Path.home()).expanduser().resolve()


def _logical_under(path: Path, root: Path) -> bool:
    try:
        Path(os.path.normpath(str(path))).relative_to(root)
        return True
    except ValueError:
        return False


def _expand_owner_text(raw: str, root: Path) -> Path:
    text = raw.strip()
    if text.startswith("~"):
        rest = text[1:].lstrip("/\\")
        return (root / rest) if rest else root
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = root / path
    return Path(os.path.normpath(str(path)))


def _xdg_user_dirs(home: Path) -> dict[str, Path]:
    cfg = home / ".config" / "user-dirs.dirs"
    if not cfg.is_file():
        return {}
    try:
        text = cfg.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[str, Path] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("XDG_") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        raw = raw.strip().strip('"').replace("$HOME", str(home))
        label = key.removeprefix("XDG_").removesuffix("_DIR").lower()
        path = Path(os.path.normpath(raw))
        out[label] = path
        out[f"{label}s"] = path
    return out


def _owner_candidates(wanted: Path, root: Path) -> list[Path]:
    found = [wanted]
    try:
        rel = wanted.relative_to(root)
    except ValueError:
        return found
    if len(rel.parts) != 1:
        return found
    key = rel.parts[0].lower()
    xdg = _xdg_user_dirs(root)
    if key in xdg:
        found.append(xdg[key])
    for alias in _FOLDER_ALIASES.get(key, ()):
        found.append(root / alias)
    unique: list[Path] = []
    for item in found:
        if item not in unique:
            unique.append(item)
    return unique


def inspect_owner_path(
    raw: str,
    home: Path | None = None,
    *,
    must_exist: bool = True,
    as_dir: bool = False,
) -> tuple[Path | None, str]:
    """Resolve a path under the owner home. Jail is the logical path, not the symlink target."""
    text = (raw or "").strip() or ("." if as_dir else "")
    if not text:
        return None, "path required"
    root = _owner_home(home)
    wanted = _expand_owner_text(text, root)
    last = "path is outside the home"
    for candidate in _owner_candidates(wanted, root):
        if not _logical_under(candidate, root):
            last = "path is outside the home"
            continue
        try:
            resolved = candidate.resolve()
        except OSError:
            last = "folder not found" if as_dir else "file not found"
            continue
        if must_exist:
            if as_dir:
                if resolved.is_dir():
                    return resolved, ""
                last = "not a folder" if resolved.exists() else "folder not found"
            else:
                if resolved.is_file():
                    return resolved, ""
                last = "not a file" if resolved.exists() else "file not found"
        else:
            if as_dir and resolved.exists() and not resolved.is_dir():
                last = "not a folder"
                continue
            return resolved if resolved.exists() else candidate, ""
    return None, last


def resolve_owner_path(
    raw: str,
    home: Path | None = None,
    *,
    must_exist: bool = True,
    as_dir: bool = False,
) -> Path | None:
    """Only paths under the owner's home. Used by /local/owner-*."""
    path, _err = inspect_owner_path(raw, home, must_exist=must_exist, as_dir=as_dir)
    return path


def _owner_path_status(error: str) -> int:
    if "outside" in error:
        return 403
    if "not found" in error:
        return 404
    return 400


def owner_downloads_dir(home: Path | None = None) -> Path:
    root = _owner_home(home)
    found, _err = inspect_owner_path("~/Downloads", root, must_exist=True, as_dir=True)
    if found is not None:
        return found
    dest = root / "Downloads"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def unique_download_dest(folder: Path, name: str) -> Path:
    safe = Path(str(name or "file").replace("\x00", "")).name.strip() or "file"
    dest = folder / safe
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    for index in range(2, 1000):
        cand = folder / f"{stem}-{index}{suffix}"
        if not cand.exists():
            return cand
    return folder / f"{stem}-{os.getpid()}{suffix}"

