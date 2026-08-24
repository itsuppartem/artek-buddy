"""Validate pip-audit ignore rows. Used by the quality job, not an HTTP route."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_IGNORE_PATH = Path(".github/pip-audit-ignore.txt")
RUNTIME_PACKAGES = frozenset({"fastapi", "starlette"})


class IgnoreFileError(ValueError):
    """A row is missing id, package, YYYY-MM-DD expiry, or a reason."""


@dataclass(frozen=True)
class IgnoreRow:
    vuln_id: str
    package: str
    expires: date
    reason: str
    line_no: int


def parse_ignore_file(path: Path) -> list[IgnoreRow]:
    rows: list[IgnoreRow] = []
    text = path.read_text(encoding="utf-8")
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 3)
        if len(parts) < 4:
            raise IgnoreFileError(f"{path}:{line_no}: expected id package YYYY-MM-DD reason")
        vuln_id, package, expiry_text, reason = parts
        reason = reason.strip()
        if not reason:
            raise IgnoreFileError(f"{path}:{line_no}: expected id package YYYY-MM-DD reason")
        try:
            expires = date.fromisoformat(expiry_text)
        except ValueError as exc:
            raise IgnoreFileError(f"{path}:{line_no}: expiry must be YYYY-MM-DD") from exc
        rows.append(
            IgnoreRow(
                vuln_id=vuln_id,
                package=package,
                expires=expires,
                reason=reason,
                line_no=line_no,
            )
        )
    return rows


def check_ignore_file(path: Path, *, today: date | None = None) -> list[str]:
    when = today or date.today()
    try:
        rows = parse_ignore_file(path)
    except IgnoreFileError as exc:
        return [str(exc)]
    errors: list[str] = []
    for row in rows:
        if row.package.lower() in RUNTIME_PACKAGES:
            errors.append(
                f"{path}:{row.line_no}: {row.vuln_id} ignores runtime package {row.package}"
            )
        if row.expires < when:
            errors.append(
                f"{path}:{row.line_no}: {row.vuln_id} expired on {row.expires.isoformat()}"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="artek_buddy.pip_audit_ignore")
    parser.add_argument(
        "path",
        nargs="?",
        default=str(DEFAULT_IGNORE_PATH),
        help="ignore file with id package YYYY-MM-DD reason rows",
    )
    args = parser.parse_args(argv)
    errors = check_ignore_file(Path(args.path))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
