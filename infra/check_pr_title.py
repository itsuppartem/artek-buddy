#!/usr/bin/env python3
"""Validate pull request titles against Conventional Commits formatting."""

from __future__ import annotations

import os
import re
import sys

CONVENTIONAL_TITLE_RE = re.compile(
    r"^(fix|feat|docs|style|refactor|perf|test|build|ci|chore|revert|release)"
    r"(\([a-zA-Z0-9._-]+\))?!?:\s+.+$"
)


def is_valid_pr_title(title: str, user: str = "") -> bool:
    clean_user = (user or "").strip().lower()
    if "dependabot" in clean_user:
        return True

    clean_title = (title or "").strip()
    if not clean_title:
        return False

    return bool(CONVENTIONAL_TITLE_RE.match(clean_title))


def main(argv: list[str]) -> int:
    title = argv[1] if len(argv) > 1 else os.environ.get("PR_TITLE", "")
    user = argv[2] if len(argv) > 2 else os.environ.get("PR_USER", "")

    if not title:
        # Not running in a PR context or empty title
        return 0

    if not is_valid_pr_title(title, user):
        print(
            f"Error: PR title '{title}' must follow Conventional Commits.\n"
            "Format: <type>(<scope>): <description> or <type>: <description>\n"
            "Types:  fix, feat, docs, style, refactor, perf, test, build, ci, chore, revert\n"
            "Examples:\n"
            "  fix(host): pair the Funnel URL without forbidden\n"
            "  docs(security): clarify token disclosure vs abuse\n"
            "  ci: publish JUnit and coverage summaries",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
