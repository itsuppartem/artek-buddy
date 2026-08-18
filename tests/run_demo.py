#!/usr/bin/env python3
"""Record the README demo against a throwaway host. Never the live :8080 stack."""

from __future__ import annotations

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
MEDIA = ROOT / "media"
IMAGE = os.environ.get("TEST_PG_IMAGE", "postgres:16-alpine")
PG_NAME = os.environ.get("ARTEK_DEMO_PG_NAME", "artek-buddy-demo-pg")
PG_PORT = os.environ.get("ARTEK_DEMO_PG_PORT", "55434")
HOST_PORT = os.environ.get("ARTEK_DEMO_HOST_PORT", "18081")
USER = "artek"
PASSWORD = "artek"
DATABASE = "artek_buddy_demo"
TOKEN = "ui-e2e-token"
KEEP_BOX_PREFIXES = ("artek-bot-bot_f04de3350788d85e",)
FAKE_NOVNC_HTML = b"""<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#f8f9fa;color:#202122;font:15px/1.5 sans-serif}
.bar{background:#fff;border-bottom:1px solid #a2a9b1;padding:10px 16px;font:13px sans-serif}
.bar b{color:#3366cc}
.page{max-width:720px;margin:28px auto;padding:0 20px}
h1{font:28px/1.2 sans-serif;border-bottom:1px solid #a2a9b1;padding-bottom:8px;margin:0 0 16px}
.box{float:right;width:210px;margin:0 0 12px 16px;padding:10px;border:1px solid #a2a9b1;background:#f8f9fa;font-size:13px}
</style></head><body>
<div class="bar"><b>Chromium</b> &nbsp; en.wikipedia.org/wiki/Belgrade</div>
<div class="page"><div class="box">Capital at the Danube and Sava</div>
<h1>Belgrade</h1>
<p>Belgrade is the capital of Serbia. Kalemegdan, Skadarlija, and the Temple of Saint Sava sit on this Team computer desktop.</p>
<canvas id="screen" width="8" height="8"></canvas>
</div></body></html>"""


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
    for port in (16080, 16081):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), _FakeNovnc)
        except OSError as err:
            print(f"run_demo: fake noVNC :{port} unavailable ({err})", file=sys.stderr)
            continue
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        servers.append(httpd)
    return servers


def _sandbox_boxes() -> set[str]:
    docker = shutil.which("docker")
    if docker is None:
        return set()
    raw = subprocess.check_output(
        [docker, "ps", "-a", "--filter", "name=artek-bot-", "--format", "{{.Names}}"],
        text=True,
    )
    return {line.strip() for line in raw.splitlines() if line.strip()}


def _live_host_token() -> str:
    docker = _docker()
    try:
        token = subprocess.check_output(
            [docker, "exec", "artek-buddy", "printenv", "AGENT_HTTP_TOKEN"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError as err:
        raise SystemExit("run_demo: live host is down; real Chromium needs the supervisor") from err
    if not token:
        raise SystemExit("run_demo: live host token is empty")
    return token


def _cleanup_new_boxes(before: set[str]) -> None:
    docker = shutil.which("docker")
    if docker is None:
        return
    for name in sorted(_sandbox_boxes() - before):
        if name.startswith(KEEP_BOX_PREFIXES):
            continue
        subprocess.call([docker, "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        home = ROOT / "data" / "homes" / name.removeprefix("artek-bot-")
        if home.is_dir():
            subprocess.call(["sudo", "rm", "-rf", str(home)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _docker() -> str:
    path = shutil.which("docker")
    if path is None:
        print("run_demo: docker is required", file=sys.stderr)
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
    raise SystemExit(f"run_demo: test postgres did not become ready: {last}")


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
    raise SystemExit(f"run_demo: isolated host did not become ready: {last}")


def _write_unpaired_home(home: Path, host_url: str) -> None:
    cfg = home / ".config" / "artek-buddy"
    cfg.mkdir(parents=True)
    (cfg / "url").write_text(host_url + "\n", encoding="utf-8")


def _publish_video() -> Path | None:
    results = WEB / "test-results"
    videos = sorted(results.rglob("*.webm"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not videos:
        print("run_demo: no Playwright video found", file=sys.stderr)
        return None
    MEDIA.mkdir(exist_ok=True)
    dest = MEDIA / "demo.webm"
    shutil.copy2(videos[0], dest)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        mp4 = MEDIA / "demo.mp4"
        subprocess.call(
            [
                ffmpeg,
                "-y",
                "-i",
                str(dest),
                "-an",
                "-vf",
                "scale=1280:-2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-crf",
                "28",
                "-movflags",
                "+faststart",
                str(mp4),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if mp4.exists() and mp4.stat().st_size > 0:
            print(f"run_demo: wrote {mp4} ({mp4.stat().st_size} bytes)")
            return mp4
    print(f"run_demo: wrote {dest} ({dest.stat().st_size} bytes)")
    return dest


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
        print("run_demo: could not start test postgres", file=sys.stderr)
        return 1

    host: subprocess.Popen[bytes] | None = None
    novnc: list[ThreadingHTTPServer] = []
    boxes_before = _sandbox_boxes()
    try:
        live_token = _live_host_token()
        _wait_postgres(database_url)
        scratch = Path(tempfile.mkdtemp(prefix="artek-ui-demo-"))
        data_dir = scratch / "data"
        cwd_dir = scratch / "cwd"
        home = scratch / "home"
        data_dir.mkdir()
        cwd_dir.mkdir()
        _write_unpaired_home(home, host_url)

        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(ROOT / "src"),
                "DATABASE_URL": database_url,
                "AGENT_HTTP_TOKEN": live_token,
                "AGENT_RUNTIME": "scripted",
                "SANDBOX_PROVIDER": "docker",
                "SANDBOX_SUPERVISOR_URL": "http://127.0.0.1:7091",
                "HTTP_HOST": "127.0.0.1",
                "HTTP_PORT": str(HOST_PORT),
                "AGENT_DATA_DIR": str(data_dir),
                "AGENT_CWD": str(cwd_dir),
                "CURSOR_API_KEY": "",
                "ARTEK_SCREEN_STARTUP_RETRY_SECONDS": "25",
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
                "ARTEK_E2E_TOKEN": live_token,
                "ARTEK_DEMO": "1",
            }
        )
        npx = shutil.which("npx", path=play_env["PATH"])
        if npx is None:
            print("run_demo: npx is missing; install Node", file=sys.stderr)
            return 1
        code = subprocess.call(
            [npx, "playwright", "test", "-c", "playwright.demo.config.ts"],
            cwd=WEB,
            env=play_env,
        )
        if code == 0:
            _publish_video()
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
        _cleanup_new_boxes(boxes_before)
        subprocess.call([docker, "rm", "-f", PG_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    raise SystemExit(main())
