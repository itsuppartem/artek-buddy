from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Never inherit the Pi .env / ./data / live DATABASE_URL.
# Packaged UI/live jobs mint AGENT_HTTP_TOKEN into GITHUB_ENV for Compose; keep it.
if os.environ.get("ARTEK_LIVE") != "1":
    _root = Path(tempfile.mkdtemp(prefix="artek-pytest-"))
    if not os.environ.get("ARTEK_CI_ENV"):
        os.environ["AGENT_HTTP_TOKEN"] = "ci-host-token-aabbccddeeff001122334455"
    os.environ["AGENT_RUNTIME"] = "scripted"
    os.environ["SANDBOX_PROVIDER"] = "fake"
    os.environ["CONSENT_AUTO"] = "ask"
    os.environ["CURSOR_API_KEY"] = ""
    os.environ["COMPOSIO_API_KEY"] = ""
    os.environ["CURSOR_MODEL"] = "scripted"
    os.environ["DATABASE_URL"] = os.environ.get(
        "ARTEK_TEST_DATABASE_URL",
        "postgresql://artek:ci-postgres-only@127.0.0.1:5432/artek_buddy",
    )
    os.environ["AGENT_DATA_DIR"] = str(_root / "data")
    os.environ["AGENT_CWD"] = str(_root / "workspace")
    (_root / "data").mkdir()
    (_root / "workspace").mkdir()

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.failed and report.when == "call" and report.longrepr:
        print("\n----- immediate failure -----", flush=True)
        print(report.longrepr, flush=True)
        print("----- end immediate failure -----\n", flush=True)


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    del exitstatus, config
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    stats = terminalreporter.stats
    passed = len(stats.get("passed", []))
    failed = len(stats.get("failed", []))
    skipped = len(stats.get("skipped", []))
    with open(summary, "a", encoding="utf-8") as handle:
        handle.write(f"- pytest passed: {passed}, failed: {failed}, skipped: {skipped}\n")


@pytest.fixture
def host_token() -> str:
    return os.environ["AGENT_HTTP_TOKEN"]


@pytest.fixture
def auth_header(host_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {host_token}"}
