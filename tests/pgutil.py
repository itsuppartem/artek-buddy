from __future__ import annotations

import os
import unittest
from urllib.parse import urlparse


def is_live_compose_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (5432 if parsed.scheme.startswith("postgres") else None)
    database = (parsed.path or "").lstrip("/")
    return host in {"127.0.0.1", "localhost"} and port == 5432 and database == "artek_buddy"


def require_test_db() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        raise unittest.SkipTest("TEST_DATABASE_URL is unset; run make test-integration")
    if is_live_compose_url(url):
        raise unittest.SkipTest("refusing the live compose database; use a throwaway Postgres")
    return url


def open_test_store():
    from artek_buddy.db.history import HistoryStore

    url = require_test_db()
    store = HistoryStore(url)
    try:
        store.open()
        store.apply_migrations()
    except Exception as err:
        store.close()
        raise unittest.SkipTest(f"test postgres unavailable: {err}") from err
    return store
