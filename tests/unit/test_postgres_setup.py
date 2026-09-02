from __future__ import annotations

import pytest
from tests.api.postgres_setup import report_postgres_setup_error


def test_report_postgres_setup_error_fails_in_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("ARTEK_ALLOW_DB_SKIP", "1")
    with pytest.raises(pytest.fail.Exception, match="checksum"):
        report_postgres_setup_error(RuntimeError("checksum"))


def test_report_postgres_setup_error_skips_with_local_opt_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("ARTEK_ALLOW_DB_SKIP", "1")
    with pytest.raises(pytest.skip.Exception, match="postgres unavailable"):
        report_postgres_setup_error(RuntimeError("checksum"))


def test_report_postgres_setup_error_fails_locally_without_opt_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("ARTEK_ALLOW_DB_SKIP", raising=False)
    with pytest.raises(pytest.fail.Exception, match="IntegrityError"):
        report_postgres_setup_error(Exception("IntegrityError"))
