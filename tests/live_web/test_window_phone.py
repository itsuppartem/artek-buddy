from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import unique_bot
from tests.live_web.helpers import (
    create_named_bot_phone,
    expect_bot_in_chats,
    open_phone_tab,
    pair_host_page,
)

pytestmark = pytest.mark.live


def test_host_page_pairs_and_stacks_on_iphone_11_pro(page: Page, host_url: str) -> None:
    box = page.viewport_size
    assert box == {"width": 375, "height": 812}
    pair_host_page(page, host_url)
    expect(page.get_by_test_id("phone-desk-pad")).to_have_count(0)
    name = unique_bot("PhoneWin")
    create_named_bot_phone(page, name)
    expect(page.get_by_test_id("thread-header")).to_contain_text(name, timeout=8_000)
    expect_bot_in_chats(page, name)
    open_phone_tab(page, "desk")
    expect(page.get_by_test_id("new-memory")).to_be_visible(timeout=8_000)
    page.get_by_title("Close panel").click()
    expect(page.get_by_test_id("phone-tab-chat")).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("thread-header")).to_contain_text(name)


def test_host_page_home_screen_hint_leaves_models_tappable(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    expect(page.get_by_test_id("home-screen-hint")).to_be_visible()
    open_phone_tab(page, "chats")
    expect(page.get_by_test_id("home-screen-hint")).to_be_visible()
    page.get_by_test_id("open-models").click()
    expect(page.get_by_test_id("models-pane")).to_be_visible(timeout=8_000)
