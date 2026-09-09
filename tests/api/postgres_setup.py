from __future__ import annotations

import os

import pytest


def ci_is_set() -> bool:
    return os.environ.get("CI", "").strip().lower() in {"1", "true", "yes"}


def allow_db_skip() -> bool:
    return os.environ.get("ARTEK_ALLOW_DB_SKIP", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def report_postgres_setup_error(err: BaseException) -> None:
    name = type(err).__name__
    if allow_db_skip() and not ci_is_set():
        pytest.skip(f"postgres unavailable: {name}")
    pytest.fail(f"postgres setup failed: {name}: {err}")
