from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "infra" / "junit_summary.py"

sys.path.insert(0, str(ROOT / "infra"))
from junit_summary import format_junit_summary, redact  # type: ignore[import-not-found]


def test_redact_masks_secrets() -> None:
    text = (
        "Error with crsr_1234567890abcdef and Bearer mytoken123 and dev_device999 "
        "AGENT_HTTP_TOKEN=secret123 and code TVVX-857N"
    )
    cleaned = redact(text)
    assert "crsr_" not in cleaned
    assert "mytoken123" not in cleaned
    assert "dev_device" not in cleaned
    assert "secret123" not in cleaned
    assert "TVVX-857N" not in cleaned
    assert "[redacted]" in cleaned
    assert "XXXX-XXXX" in cleaned


def test_format_junit_summary_missing_file(tmp_path: Path) -> None:
    assert format_junit_summary(tmp_path / "missing.xml") == ""


def test_format_junit_summary_invalid_xml(tmp_path: Path) -> None:
    bad_xml = tmp_path / "bad.xml"
    bad_xml.write_text("<not-xml", encoding="utf-8")
    summary = format_junit_summary(bad_xml)
    assert "Failed to parse" in summary


def test_format_junit_summary_passed(tmp_path: Path) -> None:
    junit = tmp_path / "junit-backend.xml"
    junit.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2" failures="0" errors="0" skipped="1" time="1.23">
    <testcase classname="tests.test_a" name="test_one" time="0.5"/>
    <testcase classname="tests.test_a" name="test_two" time="0.73">
      <skipped message="reason"/>
    </testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )
    summary = format_junit_summary(junit)
    assert "### ✅ Backend: 1 passed, 1 skipped in 1.23s" in summary


def test_format_junit_summary_failed_redacts_and_tables(tmp_path: Path) -> None:
    junit = tmp_path / "junit-ui.xml"
    junit.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="2" failures="1" errors="0" skipped="0" time="2.45">
  <testcase classname="tests.live.test_boot" name="test_pair">
    <failure message="AssertionError: token dev_secret999 did not match">Traceback here</failure>
  </testcase>
  <testcase classname="tests.live.test_boot" name="test_ok"/>
</testsuite>
""",
        encoding="utf-8",
    )
    summary = format_junit_summary(junit)
    assert "### ❌ Ui Failures (1/2)" in summary
    assert "| `tests.live.test_boot::test_pair` |" in summary
    assert "dev_secret999" not in summary
    assert "[redacted]" in summary


def test_main_cli(tmp_path: Path) -> None:
    junit = tmp_path / "junit-backend.xml"
    junit.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="1" failures="0" errors="0" skipped="0" time="0.10">
  <testcase classname="tests.test_b" name="test_pass"/>
</testsuite>
""",
        encoding="utf-8",
    )
    ran = subprocess.run(
        [sys.executable, str(SCRIPT), str(junit)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.returncode == 0
    assert "### ✅ Backend: 1 passed in 0.10s" in ran.stdout
