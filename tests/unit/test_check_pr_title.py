from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "infra" / "check_pr_title.py"

sys.path.insert(0, str(ROOT / "infra"))
from check_pr_title import is_valid_pr_title  # type: ignore[import-not-found]


def test_valid_conventional_titles() -> None:
    valid = [
        "fix: resolve null check",
        "fix(host): pair the Funnel URL without forbidden",
        "feat(client): add Appearance toggle",
        "docs(security): clarify leak vs abuse",
        "ci: publish JUnit and coverage summaries",
        "chore(deps): bump pydantic to 2.14",
        "refactor(db): extract history store query",
        "style: format keysym definitions",
        "perf(engine): reduce screen encode latency",
        "test(unit): add coverage for title checker",
        "build(deb): package new client release",
        "revert: revert recent migration",
        "feat(api)!: break backward compatibility",
    ]
    for title in valid:
        assert is_valid_pr_title(title), f"Expected valid: {title}"


def test_invalid_titles() -> None:
    invalid = [
        "",
        "   ",
        "Fixed a bug",
        "Update README.md",
        "wip",
        "random: title here",
        "fix no colon",
        "feat(): empty scope",
    ]
    for title in invalid:
        assert not is_valid_pr_title(title), f"Expected invalid: {title}"


def test_dependabot_bypasses_check() -> None:
    assert is_valid_pr_title("Bump package from 1.0 to 2.0", user="dependabot[bot]")
    assert is_valid_pr_title("Bump package", user="dependabot")


def test_main_cli_exit_codes() -> None:
    ok = subprocess.run(
        [sys.executable, str(SCRIPT), "fix(host): resolve leak"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0

    fail = subprocess.run(
        [sys.executable, str(SCRIPT), "bad title without type"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert fail.returncode == 1
    assert "Error: PR title" in fail.stderr
