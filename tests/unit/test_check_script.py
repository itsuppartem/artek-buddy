from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check.sh"
MAKEFILE = ROOT / "Makefile"


def test_check_script_exists_and_executable() -> None:
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def test_check_script_help_describes_job_mapping() -> None:
    ran = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True, check=False)
    assert ran.returncode == 0
    assert "Usage: ./scripts/check.sh" in ran.stdout
    assert "quality, backend, client/web" in ran.stdout
    assert "ui, ui_web, live, live_web, scan (Trivy), CodeQL" in ran.stdout


def test_check_script_dry_run_lists_commands() -> None:
    ran = subprocess.run([str(SCRIPT), "--dry-run"], capture_output=True, text=True, check=False)
    assert ran.returncode == 0
    assert "Ruff format check" in ran.stdout
    assert "Ruff linter check" in ran.stdout
    assert "Mypy type check" in ran.stdout
    assert "Pip-audit dependencies" in ran.stdout
    assert "Pytest unit & API suite" in ran.stdout
    assert "Coverage floors gate" in ran.stdout


def test_makefile_has_check_target() -> None:
    assert MAKEFILE.is_file()
    content = MAKEFILE.read_text(encoding="utf-8")
    assert "check:" in content
    assert "./scripts/check.sh" in content
