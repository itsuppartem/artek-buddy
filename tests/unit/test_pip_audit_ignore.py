from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from artek_buddy.pip_audit_ignore import (
    IgnoreFileError,
    check_ignore_file,
    main,
    parse_ignore_file,
)

ROOT = Path(__file__).resolve().parents[2]
IGNORE_PATH = ROOT / ".github" / "pip-audit-ignore.txt"


def _pinned(text: str, name: str) -> str:
    needle = f"{name}=="
    for raw in text.splitlines():
        line = raw.strip().strip(",").strip('"').strip("'")
        if line.startswith(needle):
            return line[len(needle) :]
    raise AssertionError(f"{name} is not pinned")


def _version_tuple(pin: str) -> tuple[int, ...]:
    return tuple(int(part) for part in pin.split(".")[:3])


def test_parser_reads_id_package_expiry_and_reason(tmp_path: Path) -> None:
    path = tmp_path / "ignore.txt"
    path.write_text(
        "# comment\n\nPYSEC-2026-1845 pytest 2026-12-31 not in the host image\n",
        encoding="utf-8",
    )
    rows = parse_ignore_file(path)
    assert len(rows) == 1
    assert rows[0].vuln_id == "PYSEC-2026-1845"
    assert rows[0].package == "pytest"
    assert rows[0].expires == date(2026, 12, 31)
    assert rows[0].reason == "not in the host image"


def test_parser_rejects_a_row_without_a_reason(tmp_path: Path) -> None:
    path = tmp_path / "ignore.txt"
    path.write_text("PYSEC-2026-1 pytest 2026-12-31\n", encoding="utf-8")
    with pytest.raises(IgnoreFileError, match="reason"):
        parse_ignore_file(path)


def test_parser_rejects_a_bad_expiry_date(tmp_path: Path) -> None:
    path = tmp_path / "ignore.txt"
    path.write_text("PYSEC-2026-1 pytest 2026-13-01 leftover in ci\n", encoding="utf-8")
    with pytest.raises(IgnoreFileError, match="YYYY-MM-DD"):
        parse_ignore_file(path)


def test_checker_rejects_an_expired_row(tmp_path: Path) -> None:
    path = tmp_path / "ignore.txt"
    path.write_text(
        "PYSEC-2026-1 pytest 2026-01-01 leftover in ci\n",
        encoding="utf-8",
    )
    errors = check_ignore_file(path, today=date(2026, 8, 24))
    assert errors
    assert any("expired" in error for error in errors)


def test_checker_rejects_a_starlette_ignore(tmp_path: Path) -> None:
    path = tmp_path / "ignore.txt"
    path.write_text(
        "PYSEC-2026-161 starlette 2026-12-31 leftover runtime cve\n",
        encoding="utf-8",
    )
    errors = check_ignore_file(path, today=date(2026, 8, 24))
    assert errors
    assert any("starlette" in error.lower() for error in errors)


def test_committed_ignore_file_has_no_runtime_asgi_packages() -> None:
    rows = parse_ignore_file(IGNORE_PATH)
    names = {row.package.lower() for row in rows}
    assert not names & {"fastapi", "starlette"}


def test_committed_ignore_file_is_valid_today() -> None:
    assert check_ignore_file(IGNORE_PATH) == []


def test_cli_accepts_the_committed_ignore_file() -> None:
    assert main([str(IGNORE_PATH)]) == 0


def test_cli_exits_nonzero_when_a_row_is_expired(tmp_path: Path) -> None:
    path = tmp_path / "ignore.txt"
    path.write_text("PYSEC-2026-1 pytest 2020-01-01 leftover in ci\n", encoding="utf-8")
    assert main([str(path)]) == 1


def test_quality_job_runs_ignore_check_before_pip_audit() -> None:
    text = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    ignore_at = text.index("PYTHONPATH=src python -m artek_buddy.pip_audit_ignore")
    audit_at = text.index("python -m pip_audit ")
    assert ignore_at < audit_at


def test_host_pins_fastapi_and_starlette_past_the_runtime_advisories() -> None:
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    proj = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert _pinned(req, "fastapi") == _pinned(proj, "fastapi")
    assert _pinned(req, "starlette") == _pinned(proj, "starlette")
    assert _version_tuple(_pinned(req, "fastapi")) >= (0, 141, 1)
    assert _version_tuple(_pinned(req, "starlette")) >= (1, 1, 0)


def test_threat_model_does_not_treat_starlette_ignores_as_standing_policy() -> None:
    text = (ROOT / "THREAT-MODEL.md").read_text(encoding="utf-8")
    ghcr = next(line for line in text.splitlines() if line.startswith("| GHCR"))
    assert "Starlette/pytest audit exceptions" not in ghcr
    assert "starlette" not in ghcr.lower()
    assert "pip-audit-ignore.txt" in ghcr
