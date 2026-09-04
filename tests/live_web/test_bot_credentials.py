from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import unique_bot
from tests.live_web.helpers import create_named_bot_phone, open_settings_phone, pair_host_page
from tests.support import mask_secret

pytestmark = pytest.mark.live


def test_host_page_settings_arbitrary_secret_last_four(page: Page, host_url: str) -> None:
    name = unique_bot("PhTok")
    secret = "ghp_" + ("A" * 36)
    mask_secret(secret)
    pair_host_page(page, host_url)
    create_named_bot_phone(page, name)
    open_settings_phone(page)
    expect(page.get_by_test_id("bot-credentials")).to_be_visible()
    expect(page.get_by_test_id("bot-credentials")).to_contain_text("host credential broker")
    page.get_by_test_id("bot-credential-add-name").fill("DEPLOY_KEY")
    page.get_by_test_id("bot-credential-add-secret").fill(secret)
    page.get_by_test_id("bot-credential-add-save").click()
    expect(page.get_by_test_id("bot-credential-deploy-key-status")).to_contain_text("••••AAAA")
    page.get_by_test_id("bot-credential-deploy-key-forget").click()
    expect(page.get_by_test_id("bot-credential-deploy-key-status")).to_have_count(0)


def test_host_page_settings_named_token_last_four(page: Page, host_url: str) -> None:
    name = unique_bot("PhTokN")
    secret = "reg_" + ("Z" * 24)
    mask_secret(secret)
    pair_host_page(page, host_url)
    create_named_bot_phone(page, name)
    open_settings_phone(page)
    page.get_by_test_id("bot-credential-add-name").fill("REGISTRY_TOKEN")
    page.get_by_test_id("bot-credential-add-secret").fill(secret)
    page.get_by_test_id("bot-credential-add-save").click()
    expect(page.get_by_test_id("bot-credential-registry-token-status")).to_contain_text("••••ZZZZ")
    page.get_by_test_id("bot-credential-registry-token-forget").click()
    expect(page.get_by_test_id("bot-credential-registry-token-status")).to_have_count(0)
