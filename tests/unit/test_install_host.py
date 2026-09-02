from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "infra" / "install-host.sh"

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "install-host-test",
    "GIT_AUTHOR_EMAIL": "install-host-test@example.com",
    "GIT_COMMITTER_NAME": "install-host-test",
    "GIT_COMMITTER_EMAIL": "install-host-test@example.com",
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, env=GIT_ENV, capture_output=True)


def _origin(tmp: Path) -> Path:
    origin = tmp / "origin"
    origin.mkdir()
    _git(origin, "init", "-b", "main")
    (origin / ".gitignore").write_text(".env\n", encoding="utf-8")
    (origin / ".env.example").write_text(
        "AGENT_HTTP_TOKEN=\nMEMORY_DB_PASSWORD=\n",
        encoding="utf-8",
    )
    _git(origin, "add", ".gitignore", ".env.example")
    _git(origin, "commit", "-m", "seed")
    _git(origin, "tag", "v0.1.0")
    (origin / "marker.txt").write_text("two\n", encoding="utf-8")
    _git(origin, "add", "marker.txt")
    _git(origin, "commit", "-m", "second")
    _git(origin, "tag", "v0.2.0")
    return origin


def _run(home: Path, repo: Path, version: str) -> subprocess.CompletedProcess[str]:
    env = {
        **GIT_ENV,
        "ARTEK_REPO": str(repo),
        "ARTEK_HOME": str(home),
        "ARTEK_VERSION": version,
        "ARTEK_INSTALL_SKIP_STACK": "1",
    }
    return subprocess.run(
        ["sh", str(SCRIPT)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_install_host_upgrades_a_clean_checkout(tmp_path: Path) -> None:
    origin = _origin(tmp_path)
    home = tmp_path / "dest"
    first = _run(home, origin, "0.1.0")
    assert first.returncode == 0, first.stderr
    assert (home / ".env.example").is_file()
    assert not (home / "marker.txt").exists()
    second = _run(home, origin, "0.2.0")
    assert second.returncode == 0, second.stderr
    assert (home / "marker.txt").read_text(encoding="utf-8") == "two\n"
    assert (home / ".env").is_file()


def test_install_host_refuses_a_dirty_tree(tmp_path: Path) -> None:
    origin = _origin(tmp_path)
    home = tmp_path / "dest"
    first = _run(home, origin, "0.1.0")
    assert first.returncode == 0, first.stderr
    (home / "dirt.txt").write_text("nope\n", encoding="utf-8")
    _git(home, "add", "dirt.txt")
    blocked = _run(home, origin, "0.2.0")
    assert blocked.returncode == 1
    assert "uncommitted changes" in blocked.stderr
    assert not (home / "marker.txt").exists()
