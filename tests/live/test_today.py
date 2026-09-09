from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import create_named_bot, pair_fresh, send_message, unique_bot

pytestmark = pytest.mark.live


def test_today_uses_host_attention_not_preview_words(
    page: Page, client_url: str, host_url: str
) -> None:
    trap = unique_bot("Trap")
    speaker = unique_bot("Consent")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, trap)
    send_message(page, "please e2e-no-questions", trap)
    expect(page.locator('[data-testid="thread-message"][data-role="bot"]').last).to_contain_text(
        "No questions remain",
        timeout=20_000,
    )
    create_named_bot(page, speaker)
    send_message(page, "e2e-consent-browse", speaker)
    expect(page.get_by_test_id("consent-card")).to_be_visible(timeout=20_000)
    page.get_by_test_id("workspace-rail").get_by_role("button", name="Today").click()
    today = page.get_by_test_id("today-view")
    expect(today).to_be_visible(timeout=8_000)
    decision = today.locator('[data-task-stage="decision"]')
    expect(decision).to_contain_text(speaker, timeout=15_000)
    expect(decision).not_to_contain_text(trap)
