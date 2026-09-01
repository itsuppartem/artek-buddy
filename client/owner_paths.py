from __future__ import annotations

import os
import re
import shlex
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
    if "\x00" in (raw or "") or "\x00" in text:
        return None, "path is outside the home"
    root = _owner_home(home)
    wanted = _expand_owner_text(text, root)
    last = "path is outside the home"
    for candidate in _owner_candidates(wanted, root):
        if not _logical_under(candidate, root):
            last = "path is outside the home"
            continue
        try:
            resolved = candidate.resolve()
        except (OSError, ValueError):
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


_FIND_FILE_WRITE_FLAGS = frozenset({"-fprint", "-fprint0", "-fprintf", "-fls"})
_OWNER_EXEC_WRAPPERS = frozenset(
    {"timeout", "nice", "nohup", "command", "ionice", "stdbuf", "time"}
)


def inspect_owner_exec_writes(command: str, home: Path | None = None) -> str:
    """Empty if git/find file-output targets stay under the owner home; else the jail error."""
    for target in _owner_exec_write_targets(command):
        path, err = inspect_owner_path(target, home, must_exist=False)
        if path is None:
            return err or "path is outside the home"
    return ""


def _owner_exec_write_targets(command: str) -> list[str]:
    text = (command or "").strip()
    if not text:
        return []
    found: list[str] = []
    for part in _shell_segments(text):
        try:
            tokens = shlex.split(part, posix=True)
        except ValueError:
            continue
        if tokens:
            found.extend(_git_find_write_targets(tokens))
    return found


def _shell_segments(text: str) -> list[str]:
    """Split on &&, ||, ;, |, and newlines without a nested-space regex."""
    parts: list[str] = []
    start = 0
    index = 0
    length = len(text)
    while index < length:
        pair = text[index : index + 2]
        char = text[index]
        if pair in {"&&", "||"} or char in ";|\n":
            chunk = text[start:index].strip()
            if chunk:
                parts.append(chunk)
            index += 2 if pair in {"&&", "||"} else 1
            start = index
            continue
        index += 1
    chunk = text[start:].strip()
    if chunk:
        parts.append(chunk)
    return parts


def _git_find_write_targets(tokens: list[str]) -> list[str]:
    index = 0
    while index < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[index]):
        index += 1
    while index < len(tokens):
        name = tokens[index].rsplit("/", 1)[-1]
        if name == "env" and index + 1 < len(tokens):
            index += 1
            while index < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[index]):
                index += 1
            continue
        if name in _OWNER_EXEC_WRAPPERS:
            index += 1
            while index < len(tokens) and (
                tokens[index].startswith("-") or re.match(r"^[0-9.]+[smh]?$", tokens[index])
            ):
                index += 1
            continue
        break
    rest = tokens[index:]
    if not rest:
        return []
    name = rest[0].rsplit("/", 1)[-1]
    if name == "git":
        return _git_write_targets(rest)
    if name == "find":
        return _find_file_write_targets(rest)
    return []


def _git_write_targets(tokens: list[str]) -> list[str]:
    found: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--output" and index + 1 < len(tokens):
            found.append(tokens[index + 1])
            index += 2
            continue
        if token.startswith("--output=") and not token.startswith("--output-indicator"):
            found.append(token.split("=", 1)[1])
            index += 1
            continue
        if token == "-C" and index + 1 < len(tokens):
            found.append(tokens[index + 1])
            index += 2
            continue
        if token in {"--git-dir", "--work-tree"} and index + 1 < len(tokens):
            found.append(tokens[index + 1])
            index += 2
            continue
        if token.startswith("--git-dir=") or token.startswith("--work-tree="):
            found.append(token.split("=", 1)[1])
            index += 1
            continue
        index += 1
    return found


def _find_file_write_targets(tokens: list[str]) -> list[str]:
    found: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in _FIND_FILE_WRITE_FLAGS and index + 1 < len(tokens):
            found.append(tokens[index + 1])
            index += 2
            continue
        index += 1
    return found


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
    if safe in {".", ".."}:
        safe = "file"
    dest = folder / safe
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    for index in range(2, 1000):
        cand = folder / f"{stem}-{index}{suffix}"
        if not cand.exists():
            return cand
    return folder / f"{stem}-{os.getpid()}{suffix}"
