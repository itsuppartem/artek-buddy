from __future__ import annotations

import subprocess
import time

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import ensure_bot, pair_fresh, send_message

pytestmark = [pytest.mark.live, pytest.mark.model, pytest.mark.timeout(400)]


def _ensure_paired(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    ensure_bot(page, "Grok")


def _chromium_running() -> bool:
    try:
        raw = subprocess.check_output(
            ["docker", "ps", "--format", "{{.Names}}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return False
    names = [line.strip() for line in raw.splitlines() if line.startswith("artek-bot-")]
    for name in names:
        try:
            out = subprocess.check_output(
                ["docker", "exec", name, "bash", "-lc", "pgrep -x chromium >/dev/null && echo yes || echo no"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            continue
        if "yes" in out:
            return True
    return False


def test_real_model_replies(page: Page, client_url: str, host_url: str) -> None:
    _ensure_paired(page, client_url, host_url)
    send_message(page, "Reply with the single word pong and nothing else.", "Grok")
    expect(page.locator('[data-testid=thread-message][data-role=bot]').last).to_be_visible(timeout=180_000)
    expect(page.get_by_test_id("typing-indicator")).to_have_count(0, timeout=180_000)


def test_browse_allow_starts_chromium(page: Page, client_url: str, host_url: str) -> None:
    _ensure_paired(page, client_url, host_url)
    send_message(page, "Open https://example.com on the remote desktop. Do not skip the Allow card.", "Grok")
    card = page.get_by_test_id("consent-card")
    try:
        card.wait_for(timeout=180_000)
    except Exception:
        pytest.skip("model did not request browse consent")
    page.get_by_test_id("ask-option").filter(has_text="Allow once").click()
    deadline = time.time() + 90
    while time.time() < deadline:
        if _chromium_running():
            return
        time.sleep(2)
    raise AssertionError("chromium did not start after Allow")


def test_browse_deny_leaves_chromium_down(page: Page, client_url: str, host_url: str) -> None:
    _ensure_paired(page, client_url, host_url)
    before = _chromium_running()
    send_message(page, "Open https://example.org on the remote desktop. Wait for the Allow card.", "Grok")
    card = page.get_by_test_id("consent-card")
    try:
        card.wait_for(timeout=180_000)
    except Exception:
        pytest.skip("model did not request browse consent")
    page.get_by_test_id("ask-option").filter(has_text="Deny").click()
    time.sleep(5)
    assert _chromium_running() == before
