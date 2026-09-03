from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import unique_bot
from tests.live_web.helpers import create_named_bot_phone, pair_host_page
from tests.support import mask_secret

pytestmark = pytest.mark.live


def test_host_page_settings_github_token_last_four(page: Page, host_url: str) -> None:
    name = unique_bot("PhTok")
    secret = "ghp_" + ("A" * 36)
    mask_secret(secret)
    pair_host_page(page, host_url)
    create_named_bot_phone(page, name)
    page.get_by_test_id("thread-pane").get_by_role("button", name="Settings").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("bot-credentials")).to_be_visible()
    page.get_by_test_id("bot-credential-github-secret").fill(secret)
    page.get_by_test_id("bot-credential-github-save").click()
    expect(page.get_by_test_id("bot-credential-github-status")).to_contain_text("••••AAAA")
    page.get_by_test_id("bot-credential-github-forget").click()
    expect(page.get_by_test_id("bot-credential-github-secret")).to_be_visible()
