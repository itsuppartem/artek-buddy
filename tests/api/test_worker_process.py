from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from artek_buddy.db.history import HistoryStore
from artek_buddy.db.shaping import isoformat_utc
from artek_buddy.worker import run_once

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
PROMPT = "please e2e-thread-blocks"


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _wait_health(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            return
        except (OSError, urllib.error.URLError) as err:
            last = err
            time.sleep(0.1)
    raise AssertionError(f"host on {port} never became healthy: {last}")


def _worker_env(port: int) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["HTTP_PORT"] = str(port)
    env["AGENT_RUNTIME"] = "scripted"
    env["SANDBOX_PROVIDER"] = "fake"
    return env


def _run_worker_once(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "artek_buddy", "worker", "--once"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def _prompt_count(messages: list[dict]) -> int:
    n = 0
    for msg in messages:
        for block in msg.get("blocks") or []:
            if block.get("kind") == "text" and PROMPT in str(block.get("text") or ""):
                n += 1
                break
    return n


def test_worker_process_wakes_a_due_routine_once(postgres_ok, host_token) -> None:
    """Release worker command + env claim a due routine once over host HTTP (#368)."""
    assert callable(run_once)
    port = _free_port()
    env = _worker_env(port)
    host = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "artek_buddy.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_health(port)
        headers = {"Authorization": f"Bearer {host_token}", "Content-Type": "application/json"}
        base = f"http://127.0.0.1:{port}"
        with httpx.Client(timeout=30.0) as http:
            bot = http.post(f"{base}/v1/bots", headers=headers, json={"name": "WorkerOnce"})
            assert bot.status_code == 200, bot.text
            bot_id = bot.json()["id"]
            created = http.post(
                f"{base}/v1/routines",
                headers=headers,
                json={
                    "bot_id": bot_id,
                    "name": "Once",
                    "prompt": PROMPT,
                    "cron": "0 9 * * *",
                    "timezone": "UTC",
                    "active": True,
                },
            )
            assert created.status_code == 200, created.text
            routine_id = created.json()["id"]
            store = HistoryStore(os.environ["DATABASE_URL"])
            store.open()
            try:
                store.seed_scripted_default()
                past = isoformat_utc(datetime.now(UTC) - timedelta(minutes=2))
                with store._conn() as conn:
                    conn.execute(
                        "UPDATE routines SET next_run_at = %s, lease_until = NULL WHERE id = %s",
                        (past, routine_id),
                    )
                    conn.commit()
            finally:
                store.close()
            first = _run_worker_once(env)
            assert first.returncode == 0, first.stderr
            deadline = time.time() + 20
            snap = {}
            while time.time() < deadline:
                snap = http.get(f"{base}/v1/threads/{bot_id}", headers=headers).json()
                if _prompt_count(snap.get("messages") or []) >= 1:
                    break
                time.sleep(0.2)
            assert _prompt_count(snap.get("messages") or []) == 1
            run = snap.get("run") or {}
            if run.get("id"):
                until = time.time() + 15
                while time.time() < until:
                    snap = http.get(f"{base}/v1/threads/{bot_id}", headers=headers).json()
                    status = (snap.get("run") or {}).get("status")
                    if status in {"completed", "failed", "cancelled"}:
                        break
                    time.sleep(0.2)
            second = _run_worker_once(env)
            assert second.returncode == 0, second.stderr
            later = http.get(f"{base}/v1/threads/{bot_id}", headers=headers).json()
            assert _prompt_count(later.get("messages") or []) == 1
    finally:
        host.terminate()
        try:
            host.wait(timeout=10)
        except subprocess.TimeoutExpired:
            host.kill()
