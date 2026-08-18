#!/usr/bin/env python3
"""Playwright UI tests against a throwaway host. Never the live compose stack."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.ui_host import refuse_live_stack
WEB = ROOT / "client" / "web"
IMAGE = os.environ.get("TEST_PG_IMAGE", "postgres:16-alpine")
PG_NAME = os.environ.get("ARTEK_UI_PG_NAME", "artek-buddy-ui-pg")
PG_PORT = os.environ.get("ARTEK_UI_PG_PORT", "55433")
HOST_PORT = os.environ.get("ARTEK_UI_HOST_PORT", "18080")
USER = "artek"
PASSWORD = "artek"
DATABASE = "artek_buddy_ui"
TOKEN = "ui-e2e-token"


def _docker() -> str:
    path = shutil.which("docker")
    if path is None:
        print("run_ui: docker is required for the throwaway UI host", file=sys.stderr)
        raise SystemExit(1)
    return path


def _wait_postgres(url: str, timeout: float = 40) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from artek_buddy.db.history import HistoryStore

    deadline = time.time() + timeout
    last = "not started"
    while time.time() < deadline:
        store = HistoryStore(url)
        try:
            store.open()
            store.close()
            return
        except Exception as err:
            last = str(err)
            time.sleep(0.4)
    raise SystemExit(f"run_ui: test postgres did not become ready: {last}")


def _wait_health(url: str, timeout: float = 40) -> None:
    health = f"{url.rstrip('/')}/health"
    deadline = time.time() + timeout
    last = "not started"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health, timeout=2) as resp:
                if resp.status == 200:
                    return
                last = f"status {resp.status}"
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            last = str(err)
        time.sleep(0.3)
    raise SystemExit(f"run_ui: isolated host did not become ready: {last}")


def _write_client_home(home: Path, host_url: str) -> None:
    cfg = home / ".config" / "artek-buddy"
    cfg.mkdir(parents=True)
    (cfg / "url").write_text(host_url + "\n", encoding="utf-8")
    token = cfg / "token"
    token.write_text(TOKEN + "\n", encoding="utf-8")
    token.chmod(0o600)


def main() -> int:
    host_url = f"http://127.0.0.1:{HOST_PORT}"
    database_url = f"postgresql://{USER}:{PASSWORD}@127.0.0.1:{PG_PORT}/{DATABASE}"
    refuse_live_stack(database_url, host_url)

    docker = _docker()
    subprocess.call([docker, "rm", "-f", PG_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    started = subprocess.call(
        [
            docker,
            "run",
            "-d",
            "--name",
            PG_NAME,
            "-e",
            f"POSTGRES_USER={USER}",
            "-e",
            f"POSTGRES_PASSWORD={PASSWORD}",
            "-e",
            f"POSTGRES_DB={DATABASE}",
            "-p",
            f"127.0.0.1:{PG_PORT}:5432",
            IMAGE,
            "-c",
            "fsync=off",
            "-c",
            "full_page_writes=off",
            "-c",
            "synchronous_commit=off",
        ],
        stdout=subprocess.DEVNULL,
    )
    if started != 0:
        print("run_ui: could not start test postgres", file=sys.stderr)
        return 1

    host: subprocess.Popen[bytes] | None = None
    try:
        _wait_postgres(database_url)
        scratch = Path(tempfile.mkdtemp(prefix="artek-ui-e2e-"))
        data_dir = scratch / "data"
        cwd_dir = scratch / "cwd"
        home = scratch / "home"
        data_dir.mkdir()
        cwd_dir.mkdir()
        _write_client_home(home, host_url)

        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(ROOT / "src"),
                "DATABASE_URL": database_url,
                "AGENT_HTTP_TOKEN": TOKEN,
                "AGENT_RUNTIME": "scripted",
                "SANDBOX_PROVIDER": "fake",
                "HTTP_HOST": "127.0.0.1",
                "HTTP_PORT": str(HOST_PORT),
                "AGENT_DATA_DIR": str(data_dir),
                "AGENT_CWD": str(cwd_dir),
                "CURSOR_API_KEY": "",
            }
        )
        host = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "artek_buddy.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(HOST_PORT),
                "--log-level",
                "warning",
            ],
            cwd=str(scratch),
            env=env,
            start_new_session=True,
        )
        _wait_health(host_url)

        play_env = os.environ.copy()
        node_bin = Path.home() / ".local" / "node" / "bin"
        path = play_env.get("PATH", "")
        if node_bin.is_dir() and str(node_bin) not in path.split(":"):
            play_env["PATH"] = f"{node_bin}:{path}" if path else str(node_bin)
        play_env.update(
            {
                "ARTEK_UI_ISOLATED": "1",
                "ARTEK_UI_HOST_URL": host_url,
                "ARTEK_E2E_HOME": str(home),
                "ARTEK_E2E_TOKEN": TOKEN,
            }
        )
        npx = shutil.which("npx", path=play_env["PATH"])
        if npx is None:
            print("run_ui: npx is missing; install Node", file=sys.stderr)
            return 1
        return subprocess.call([npx, "playwright", "test"], cwd=WEB, env=play_env)
    finally:
        if host is not None and host.poll() is None:
            try:
                os.killpg(host.pid, signal.SIGTERM)
            except OSError:
                host.terminate()
            try:
                host.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(host.pid, signal.SIGKILL)
                except OSError:
                    host.kill()
        subprocess.call([docker, "rm", "-f", PG_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    raise SystemExit(main())
