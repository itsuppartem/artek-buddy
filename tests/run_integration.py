#!/usr/bin/env python3
"""Run integration tests against a throwaway Postgres, never the live compose database."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get("TEST_PG_IMAGE", "postgres:16-alpine")
NAME = os.environ.get("TEST_PG_NAME", "artek-buddy-test-pg")
PORT = os.environ.get("TEST_PG_PORT", "55432")
USER = "artek"
PASSWORD = "artek"
DATABASE = "artek_buddy_test"
MODULES = (
    "tests.integration_history",
    "tests.integration_devices",
    "tests.integration_routines",
    "tests.integration_memory",
    "tests.integration_computer",
)


def _live(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 5432
    database = (parsed.path or "").lstrip("/")
    return host in {"127.0.0.1", "localhost"} and port == 5432 and database == "artek_buddy"


def _run_tests(url: str) -> int:
    if _live(url):
        print("run_integration: refusing the live compose database", file=sys.stderr)
        return 2
    env = os.environ.copy()
    env["TEST_DATABASE_URL"] = url
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.call([sys.executable, "-m", "unittest", *MODULES, "-q"], cwd=ROOT, env=env)


def _docker() -> str | None:
    return shutil.which("docker")


def _wait_ready(url: str, timeout: float = 40) -> None:
    import logging

    sys.path.insert(0, str(ROOT / "src"))
    from artek_buddy.db.history import HistoryStore

    logging.getLogger("psycopg").setLevel(logging.CRITICAL)
    logging.getLogger("psycopg.pool").setLevel(logging.CRITICAL)
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
    raise SystemExit(f"test postgres did not become ready: {last}")


def _ephemeral() -> int:
    docker = _docker()
    if docker is None:
        print("run_integration: skip (no TEST_DATABASE_URL and no docker)")
        return 0
    url = f"postgresql://{USER}:{PASSWORD}@127.0.0.1:{PORT}/{DATABASE}"
    subprocess.call([docker, "rm", "-f", NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    started = subprocess.call(
        [
            docker,
            "run",
            "-d",
            "--name",
            NAME,
            "-e",
            f"POSTGRES_USER={USER}",
            "-e",
            f"POSTGRES_PASSWORD={PASSWORD}",
            "-e",
            f"POSTGRES_DB={DATABASE}",
            "-p",
            f"127.0.0.1:{PORT}:5432",
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
        print("run_integration: could not start test postgres", file=sys.stderr)
        return 1
    try:
        _wait_ready(url)
        return _run_tests(url)
    finally:
        subprocess.call([docker, "rm", "-f", NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if url:
        return _run_tests(url)
    return _ephemeral()


if __name__ == "__main__":
    raise SystemExit(main())
