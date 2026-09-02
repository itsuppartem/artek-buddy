from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg.rows import dict_row

from artek_buddy.db.connection import MIGRATIONS_DIR
from artek_buddy.db.history import HistoryStore
from artek_buddy.db.history.store import MigrationChecksumError
from artek_buddy.db.sql_split import split_sql_statements

FIXTURE = Path(__file__).resolve().parents[1] / "unit" / "fixtures" / "semicolon_in_function.sql"
EXPECTED_TABLES = ("bots", "devices", "computers", "consent_grants", "consent_requests")


def _with_db(url: str, name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))


@pytest.fixture
def empty_database_url() -> Iterator[str]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL unset")
    name = "artek_replay_" + secrets.token_hex(4)
    admin = _with_db(url, "postgres")
    try:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f"CREATE DATABASE {name}")
    except Exception as err:
        pytest.skip(f"cannot create empty database: {type(err).__name__}")
    yield _with_db(url, name)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (name,),
        )
        conn.execute(f"DROP DATABASE IF EXISTS {name}")


def test_apply_migrations_replays_every_historical_file(empty_database_url: str) -> None:
    files = sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))
    assert len(files) == 26
    assert files[0].startswith("0001_")
    assert files[-1].startswith("0026_")

    store = HistoryStore(empty_database_url)
    try:
        store.open()
        store.apply_migrations()
    finally:
        store.close()

    with psycopg.connect(empty_database_url, row_factory=dict_row) as conn:
        applied = [
            row["id"]
            for row in conn.execute("SELECT id FROM schema_migrations ORDER BY id").fetchall()
        ]
        assert applied == files
        for table in EXPECTED_TABLES:
            row = conn.execute("SELECT to_regclass(%s) AS rel", (f"public.{table}",)).fetchone()
            assert row is not None
            assert row["rel"] is not None, table
        idx = conn.execute(
            "SELECT 1 AS ok FROM pg_indexes WHERE indexname = %s",
            ("consent_grants_uniq",),
        ).fetchone()
        assert idx is not None


def test_dollar_body_with_semicolon_applies_after_replay(empty_database_url: str) -> None:
    sql = FIXTURE.read_text(encoding="utf-8")
    statements = split_sql_statements(sql)
    naive = [part.strip() for part in sql.split(";") if part.strip()]
    assert len(statements) == 1
    assert len(naive) > 1

    store = HistoryStore(empty_database_url)
    try:
        store.open()
        store.apply_migrations()
    finally:
        store.close()

    with psycopg.connect(empty_database_url, row_factory=dict_row) as conn:
        for statement in statements:
            conn.execute(statement)
        conn.commit()
        row = conn.execute("SELECT artek_split_probe() AS n").fetchone()
        assert row is not None
        assert row["n"] == 1


def _apply_once(url: str) -> None:
    store = HistoryStore(url)
    try:
        store.open()
        store.apply_migrations()
    finally:
        store.close()


def test_applied_files_store_sha256_checksums(empty_database_url: str) -> None:
    _apply_once(empty_database_url)
    with psycopg.connect(empty_database_url, row_factory=dict_row) as conn:
        rows = conn.execute("SELECT id, checksum FROM schema_migrations ORDER BY id").fetchall()
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert [row["id"] for row in rows] == [path.name for path in files]
    for row, path in zip(rows, files, strict=True):
        assert row["checksum"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_two_parallel_apply_migrations_do_not_double_apply(
    empty_database_url: str,
) -> None:
    barrier = threading.Barrier(2)

    def run() -> None:
        store = HistoryStore(empty_database_url)
        try:
            store.open()
            barrier.wait(timeout=10)
            store.apply_migrations()
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run), pool.submit(run)]
        for fut in as_completed(futures):
            fut.result()

    files = sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))
    with psycopg.connect(empty_database_url, row_factory=dict_row) as conn:
        applied = [
            row["id"]
            for row in conn.execute("SELECT id FROM schema_migrations ORDER BY id").fetchall()
        ]
        count = conn.execute("SELECT count(*) AS n FROM schema_migrations").fetchone()
    assert applied == files
    assert count is not None
    assert count["n"] == len(files)


def test_rewritten_historical_file_fails_checksum(
    empty_database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copied = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, copied)
    monkeypatch.setattr("artek_buddy.db.history.store.MIGRATIONS_DIR", copied)
    _apply_once(empty_database_url)
    target = next(iter(sorted(copied.glob("*.sql"))))
    target.write_bytes(target.read_bytes() + b"\n-- rewritten\n")
    with pytest.raises(MigrationChecksumError, match=target.name):
        _apply_once(empty_database_url)


def test_empty_checksum_is_backfilled_on_next_apply(empty_database_url: str) -> None:
    _apply_once(empty_database_url)
    first = sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))[0]
    with psycopg.connect(empty_database_url, row_factory=dict_row) as conn:
        conn.execute("UPDATE schema_migrations SET checksum = '' WHERE id = %s", (first,))
        conn.commit()
    _apply_once(empty_database_url)
    expected = hashlib.sha256((MIGRATIONS_DIR / first).read_bytes()).hexdigest()
    with psycopg.connect(empty_database_url, row_factory=dict_row) as conn:
        row = conn.execute(
            "SELECT checksum FROM schema_migrations WHERE id = %s", (first,)
        ).fetchone()
    assert row is not None
    assert row["checksum"] == expected
