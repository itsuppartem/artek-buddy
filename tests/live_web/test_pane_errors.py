from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import fulfill_json, unique_bot
from tests.live_web.helpers import create_named_bot_phone, open_phone_tab, pair_host_page

pytestmark = pytest.mark.live


def test_host_page_models_list_error_is_not_silent(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("ListErr"))
    fulfill_json(page, "**/v1/models", 500, '{"detail":"list down"}', method="GET")
    open_phone_tab(page, "more")
    page.get_by_test_id("library-open-models").click()
    expect(page.get_by_test_id("models-error")).to_contain_text("list down")


def test_host_page_plugins_status_error_is_not_checking(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    fulfill_json(page, "**/v1/connections/status", 500, '{"detail":"status down"}', method="GET")
    open_phone_tab(page, "more")
    page.get_by_test_id("library-open-plugins").click()
    expect(page.get_by_test_id("plugins-error")).to_contain_text("status down", timeout=8_000)
    expect(page.get_by_text("Checking the key…")).to_have_count(0)
    expect(page.get_by_text("Paste a key to connect apps.")).to_have_count(0)
