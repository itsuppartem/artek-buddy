from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import ensure_bot, pair_fresh, send_message

pytestmark = pytest.mark.live


def _open_thread(page: Page, client_url: str, host_url: str, name: str) -> None:
    pair_fresh(page, client_url, host_url)
    ensure_bot(page, name)


def test_scripted_reply_appears(page: Page, client_url: str, host_url: str) -> None:
    _open_thread(page, client_url, host_url, "Scripted")
    send_message(page, "hello")
    expect(page.locator('[data-testid=thread-message][data-role=bot]').last).to_contain_text(
        "ok",
        timeout=20_000,
    )


def test_scripted_fail_shows_run_error(page: Page, client_url: str, host_url: str) -> None:
    _open_thread(page, client_url, host_url, "ScriptedFail")
    send_message(page, "please e2e-fail now")
    expect(page.get_by_test_id("run-error")).to_be_visible(timeout=20_000)


def test_scripted_consent_can_be_denied(page: Page, client_url: str, host_url: str) -> None:
    _open_thread(page, client_url, host_url, "ScriptedConsent")
    send_message(page, "e2e-consent-browse")
    card = page.get_by_test_id("consent-card")
    expect(card).to_be_visible(timeout=20_000)
    page.get_by_test_id("ask-option").filter(has_text="Deny").click()
    expect(card).to_have_attribute("data-status", "answered", timeout=20_000)
    expect(card.get_by_text("Answered")).to_be_visible()
    expect(page.get_by_test_id("ask-option")).to_have_count(0)
