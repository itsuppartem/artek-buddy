from __future__ import annotations

import importlib.util
import os
import runpy
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

CLIENT_DIR = Path(__file__).resolve().parents[2] / "client"


def _load_mux():
    spec = importlib.util.spec_from_file_location("ssh_mux_test", CLIENT_DIR / "ssh_mux.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_ssh(tmp_path: Path) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    ssh = bindir / "ssh"
    ssh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    ssh.chmod(0o755)
    return ssh


def test_missing_opt_in_keeps_owner_exec_environment_unchanged(tmp_path: Path) -> None:
    mux = _load_mux()
    ssh = _fake_ssh(tmp_path)
    home = tmp_path / "home"
    env = {"HOME": str(home), "PATH": str(ssh.parent)}

    prepared = mux.owner_exec_environment(env)

    assert prepared == env
    assert not (home / ".ssh").exists()


def test_opt_in_uses_private_short_control_path(tmp_path: Path) -> None:
    mux = _load_mux()
    ssh = _fake_ssh(tmp_path)
    home = tmp_path / ("long-home-" + "x" * 120)
    config = home / ".config" / "artek-buddy"
    config.mkdir(parents=True)
    (config / "ssh-mux").write_text("120\n", encoding="utf-8")
    env = {"HOME": str(home), "PATH": str(ssh.parent)}

    prepared = mux.owner_exec_environment(env)

    control_path = prepared["ARTEK_SSH_CONTROL_PATH"]
    socket_dir = Path(control_path).parent
    assert control_path.endswith("/%C")
    assert len(os.fsencode(control_path)) < 108
    assert stat.S_IMODE(socket_dir.stat().st_mode) == 0o700
    assert prepared["ARTEK_SSH_REAL"] == str(ssh)
    assert prepared["ARTEK_SSH_PERSIST"] == "120"
    assert prepared["PATH"].split(os.pathsep)[0] == str(CLIENT_DIR / "ssh-wrap")
    assert not (home / ".ssh").exists()


def test_invalid_persist_uses_bounded_default(tmp_path: Path) -> None:
    mux = _load_mux()
    ssh = _fake_ssh(tmp_path)
    home = tmp_path / "home"
    config = home / ".config" / "artek-buddy"
    config.mkdir(parents=True)
    (config / "ssh-mux").write_text("yes\n", encoding="utf-8")

    prepared = mux.owner_exec_environment({"HOME": str(home), "PATH": str(ssh.parent)})

    assert prepared["ARTEK_SSH_PERSIST"] == "60"


def test_wrapper_places_user_ssh_options_last(monkeypatch, tmp_path: Path) -> None:
    real = tmp_path / "ssh-real"
    real.write_text("", encoding="utf-8")
    captured: list[tuple[str, list[str]]] = []

    def fake_execv(path: str, argv: list[str]) -> None:
        captured.append((path, argv))
        raise SystemExit(0)

    monkeypatch.setattr(os, "execv", fake_execv)
    monkeypatch.setenv("ARTEK_SSH_REAL", str(real))
    monkeypatch.setenv("ARTEK_SSH_CONTROL_PATH", "/tmp/artek-test/%C")
    monkeypatch.setenv("ARTEK_SSH_PERSIST", "60")
    monkeypatch.setattr(sys, "argv", ["ssh", "-o", "ControlPath=user", "owner-host"])

    try:
        runpy.run_path(str(CLIENT_DIR / "ssh-wrap" / "ssh"), run_name="__main__")
    except SystemExit as exc:
        assert exc.code == 0

    assert captured == [
        (
            str(real),
            [
                str(real),
                "-o",
                "ControlMaster=auto",
                "-o",
                "ControlPath=/tmp/artek-test/%C",
                "-o",
                "ControlPersist=60",
                "-o",
                "ControlPath=user",
                "owner-host",
            ],
        )
    ]


def test_cleanup_exits_known_mux_sockets(monkeypatch, tmp_path: Path) -> None:
    mux = _load_mux()
    socket_dir = tmp_path / "mux"
    socket_dir.mkdir()
    socket_path = socket_dir / "abc123"
    socket_path.write_text("", encoding="utf-8")
    calls: list[list[str]] = []

    monkeypatch.setattr(
        mux.subprocess,
        "run",
        lambda argv, **_kwargs: calls.append(argv) or SimpleNamespace(returncode=0),
    )
    mux._MUX_DIRS.add(("/usr/bin/ssh", socket_dir))

    mux.cleanup_mux()

    assert calls == [["/usr/bin/ssh", "-S", str(socket_path), "-O", "exit", "unused"]]
