#!/usr/bin/env python3
"""Record Memory-panel screenshots against a throwaway host. Never the live :8080 stack.

Does not touch media/demo.*. Writes PNGs to media/memory-shots/.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.ui_host import refuse_live_stack

WEB = ROOT / "client" / "web"
SHOTS = Path(os.environ.get("ARTEK_SHOT_DIR", str(ROOT / "media" / "memory-shots")))
IMAGE = os.environ.get("TEST_PG_IMAGE", "postgres:16-alpine")
PG_NAME = os.environ.get("ARTEK_SHOT_PG_NAME", "artek-buddy-memory-shots-pg")
PG_PORT = os.environ.get("ARTEK_SHOT_PG_PORT", "55436")
HOST_PORT = os.environ.get("ARTEK_SHOT_HOST_PORT", "18082")
USER = "artek"
PASSWORD = "artek"
DATABASE = "artek_buddy_shots"
TOKEN = "ui-e2e-token"
FAKE_NOVNC_HTML = b"<html><body><canvas id='screen'></canvas></body></html>"


class _FakeNovnc(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(FAKE_NOVNC_HTML)))
        self.end_headers()
        self.wfile.write(FAKE_NOVNC_HTML)

    def log_message(self, *_args: object) -> None:
        return


def _start_fake_novnc() -> list[ThreadingHTTPServer]:
    servers: list[ThreadingHTTPServer] = []
    for port in (16082, 16083):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), _FakeNovnc)
        except OSError as err:
            print(f"run_memory_shots: fake noVNC :{port} unavailable ({err})", file=sys.stderr)
            continue
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        servers.append(httpd)
    return servers


def _docker() -> str:
    path = shutil.which("docker")
    if path is None:
        print("run_memory_shots: docker is required", file=sys.stderr)
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
    raise SystemExit(f"run_memory_shots: test postgres did not become ready: {last}")


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
    raise SystemExit(f"run_memory_shots: isolated host did not become ready: {last}")


def _write_client_home(home: Path, host_url: str) -> None:
    cfg = home / ".config" / "artek-buddy"
    cfg.mkdir(parents=True)
    (cfg / "url").write_text(host_url + "\n", encoding="utf-8")
    token = cfg / "token"
    token.write_text(TOKEN + "\n", encoding="utf-8")
    token.chmod(0o600)


def _api(host_url: str, method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{host_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8")) if raw else {}


def _seed(host_url: str) -> str:
    bot = _api(
        host_url,
        "POST",
        "/v1/bots",
        {
            "name": "Research",
            "description": "Sources, briefings, and desktop work",
            "computer_mode": "team",
        },
    )
    bot_id = bot["id"]
    cards = [
        {
            "scope": "user",
            "path": "entries/owner/place-city.md",
            "content": "Lives in Belgrade",
            "kind": "place",
        },
        {
            "scope": "user",
            "path": "entries/owner/preference-tone.md",
            "content": "No emoji",
            "kind": "preference",
        },
        {
            "scope": "user",
            "path": "entries/owner/preference-format.md",
            "content": "Prefers short answers",
            "kind": "preference",
        },
        {
            "scope": "user",
            "path": "entries/owner/preference-language.md",
            "content": "Prefers English",
            "kind": "preference",
        },
        {
            "scope": "user",
            "path": "entries/work/project-artek.md",
            "content": "Repo artek-buddy on the Pi host",
            "kind": "project",
        },
        {
            "scope": "bot",
            "bot_id": bot_id,
            "path": "entries/charter/rule-research.md",
            "content": "Research briefings, sources, and desktop work",
            "kind": "rule",
        },
    ]
    for card in cards:
        _api(host_url, "POST", "/v1/memory", card)
    listed = _api(host_url, "GET", f"/v1/memory?bot_id={bot_id}")
    docs = listed.get("documents") or []
    print(f"run_memory_shots: seeded bot={bot_id} cards={len(docs)}")
    return bot_id


def main() -> int:
    host_url = f"http://127.0.0.1:{HOST_PORT}"
    database_url = f"postgresql://{USER}:{PASSWORD}@127.0.0.1:{PG_PORT}/{DATABASE}"
    refuse_live_stack(database_url, host_url)
    SHOTS.mkdir(parents=True, exist_ok=True)

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
        print("run_memory_shots: could not start test postgres", file=sys.stderr)
        return 1

    host: subprocess.Popen[bytes] | None = None
    novnc: list[ThreadingHTTPServer] = []
    try:
        novnc = _start_fake_novnc()
        _wait_postgres(database_url)
        scratch = Path(tempfile.mkdtemp(prefix="artek-memory-shots-"))
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
                "ARTEK_SCREEN_STARTUP_RETRY_SECONDS": "0",
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
        _seed(host_url)

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
                "ARTEK_SHOT_DIR": str(SHOTS),
                "ARTEK_UI_PORT": os.environ.get("ARTEK_UI_PORT", "4178"),
            }
        )
        npx = shutil.which("npx", path=play_env["PATH"])
        if npx is None:
            print("run_memory_shots: npx is missing; install Node", file=sys.stderr)
            return 1
        code = subprocess.call(
            [npx, "playwright", "test", "-c", "playwright.memory-shots.config.ts"],
            cwd=WEB,
            env=play_env,
        )
        written = sorted(SHOTS.glob("*.png"))
        print(f"run_memory_shots: exit={code} shots={len(written)} dir={SHOTS}")
        for path in written:
            print(f"  {path.name} {path.stat().st_size}")
        return code
    finally:
        for server in novnc:
            server.shutdown()
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
