from __future__ import annotations

import atexit
import os
import shutil
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path

DEFAULT_PERSIST_SECONDS = 60
MAX_PERSIST_SECONDS = 3600
CONTROL_PATH_LIMIT = 108
_MUX_DIRS: set[tuple[str, Path]] = set()
_CLEANUP_REGISTERED = False


def _config_dir(env: Mapping[str, str]) -> Path:
    configured = (env.get("XDG_CONFIG_HOME") or "").strip()
    if configured:
        return Path(configured).expanduser() / "artek-buddy"
    return Path(env.get("HOME") or str(Path.home())).expanduser() / ".config" / "artek-buddy"


def _persist_seconds(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = handle.read(32).splitlines()
    except OSError:
        return None
    if not raw or not raw[0].strip():
        return DEFAULT_PERSIST_SECONDS
    try:
        value = int(raw[0].strip())
    except ValueError:
        return DEFAULT_PERSIST_SECONDS
    if not 1 <= value <= MAX_PERSIST_SECONDS:
        return DEFAULT_PERSIST_SECONDS
    return value


def _private_dir(path: Path) -> Path | None:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        current = path.lstat()
        if stat.S_ISLNK(current.st_mode) or not stat.S_ISDIR(current.st_mode):
            return None
        if current.st_uid != os.getuid():
            return None
        path.chmod(0o700)
    except OSError:
        return None
    return path


def _control_dir(env: Mapping[str, str]) -> Path | None:
    runtime = (env.get("XDG_RUNTIME_DIR") or "").strip()
    home = Path(env.get("HOME") or str(Path.home())).expanduser()
    candidates = []
    if runtime:
        candidates.append(Path(runtime) / "artek-buddy" / "ssh")
    candidates.append(home / ".cache" / "artek-buddy" / "ssh")
    candidates.append(Path("/tmp") / f"artek-buddy-{os.getuid()}" / "ssh")
    for candidate in candidates:
        control_path = candidate / "%C"
        if len(os.fsencode(control_path)) >= CONTROL_PATH_LIMIT:
            continue
        secured = _private_dir(candidate)
        if secured is not None:
            return secured
    return None


def _real_ssh(env: Mapping[str, str], wrapper_dir: Path) -> str | None:
    raw_path = env.get("PATH") or os.defpath
    wrapper = str(wrapper_dir.resolve())
    clean = os.pathsep.join(
        item for item in raw_path.split(os.pathsep) if item and str(Path(item).resolve()) != wrapper
    )
    return shutil.which("ssh", path=clean)


def owner_exec_environment(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    global _CLEANUP_REGISTERED

    env = dict(os.environ if environ is None else environ)
    persist = _persist_seconds(_config_dir(env) / "ssh-mux")
    if persist is None:
        return env
    wrapper_dir = Path(__file__).resolve().with_name("ssh-wrap")
    real_ssh = _real_ssh(env, wrapper_dir)
    socket_dir = _control_dir(env)
    if not real_ssh or socket_dir is None or not (wrapper_dir / "ssh").is_file():
        return env
    env["ARTEK_SSH_REAL"] = real_ssh
    env["ARTEK_SSH_CONTROL_PATH"] = str(socket_dir / "%C")
    env["ARTEK_SSH_PERSIST"] = str(persist)
    env["PATH"] = f"{wrapper_dir}{os.pathsep}{env.get('PATH') or os.defpath}"
    _MUX_DIRS.add((real_ssh, socket_dir))
    if not _CLEANUP_REGISTERED:
        atexit.register(cleanup_mux)
        _CLEANUP_REGISTERED = True
    return env


def cleanup_mux() -> None:
    for real_ssh, socket_dir in tuple(_MUX_DIRS):
        try:
            sockets = tuple(socket_dir.iterdir())
        except OSError:
            continue
        for socket_path in sockets:
            try:
                subprocess.run(
                    [real_ssh, "-S", str(socket_path), "-O", "exit", "unused"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
    _MUX_DIRS.clear()
