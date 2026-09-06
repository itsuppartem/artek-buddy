#!/usr/bin/env python3
"""Format pytest JUnit XML results as a clean Markdown summary with redacted secrets."""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REDACT_PATTERNS = [
    (re.compile(r"crsr_[A-Za-z0-9_-]+"), "[redacted]"),
    (re.compile(r"Bearer [A-Za-z0-9._~+/-]+"), "Bearer [redacted]"),
    (re.compile(r"dev_[A-Za-z0-9_-]+"), "[redacted]"),
    (re.compile(r"AGENT_HTTP_TOKEN=[^\s]+"), "AGENT_HTTP_TOKEN=[redacted]"),
    (re.compile(r"CURSOR_API_KEY=[^\s]+"), "CURSOR_API_KEY=[redacted]"),
    (re.compile(r"COMPOSIO_API_KEY=[^\s]+"), "COMPOSIO_API_KEY=[redacted]"),
    (re.compile(r"MEMORY_DB_PASSWORD=[^\s]+"), "MEMORY_DB_PASSWORD=[redacted]"),
    (re.compile(r"DATABASE_URL=postgresql:[^\s]+"), "DATABASE_URL=[redacted]"),
    (re.compile(r"[A-Z0-9]{4}-[A-Z0-9]{4}"), "XXXX-XXXX"),
]


def redact(text: str) -> str:
    for pattern, replacement in REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def format_junit_summary(xml_path: Path) -> str:
    if not xml_path.is_file():
        return ""
    try:
        tree = ET.parse(xml_path)
    except Exception as exc:
        return f"### Failed to parse test results: {exc}\n"

    root = tree.getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")

    total_tests = 0
    total_failures = 0
    total_errors = 0
    total_skipped = 0
    total_time = 0.0

    failures: list[tuple[str, str, str]] = []

    for suite in suites:
        total_tests += int(suite.attrib.get("tests", 0) or 0)
        total_failures += int(suite.attrib.get("failures", 0) or 0)
        total_errors += int(suite.attrib.get("errors", 0) or 0)
        total_skipped += int(suite.attrib.get("skipped", 0) or 0)
        try:
            total_time += float(suite.attrib.get("time", 0.0) or 0.0)
        except ValueError:
            pass

        for case in suite.findall("testcase"):
            classname = case.attrib.get("classname", "")
            name = case.attrib.get("name", "")
            failure_node = case.find("failure")
            error_node = case.find("error")
            if failure_node is not None or error_node is not None:
                node = failure_node if failure_node is not None else error_node
                msg = node.attrib.get("message", "") if node is not None else ""
                body = (node.text or "").strip() if node is not None else ""
                short_detail = msg or (body.splitlines()[0] if body else "Failed")
                failures.append((classname, name, short_detail))

    total_passed = max(0, total_tests - total_failures - total_errors - total_skipped)

    lines: list[str] = []
    suite_title = (
        xml_path.stem.replace("junit-", "")
        .replace("junit", "Test")
        .replace("-", " ")
        .replace("_", " ")
        .title()
    )
    if total_failures or total_errors:
        failed_count = total_failures + total_errors
        lines.append(f"### ❌ {suite_title} Failures ({failed_count}/{total_tests})")
        lines.append("")
        lines.append("| Test | Error |")
        lines.append("| --- | --- |")
        for cls, name, detail in failures:
            clean_detail = redact(detail).replace("|", "\\|").replace("\n", " ")
            if len(clean_detail) > 120:
                clean_detail = clean_detail[:117] + "..."
            test_id = f"{cls}::{name}" if cls else name
            lines.append(f"| `{test_id}` | `{clean_detail}` |")
        lines.append("")
    else:
        lines.append(
            f"### ✅ {suite_title}: {total_passed} passed"
            + (f", {total_skipped} skipped" if total_skipped else "")
            + f" in {total_time:.2f}s"
        )
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str]) -> int:
    for arg in argv[1:]:
        summary = format_junit_summary(Path(arg))
        if summary:
            print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
