from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    arm_page,
    bot_row,
    create_named_bot,
    mint_pairing_code,
    unique_bot,
)

pytestmark = pytest.mark.live


def test_host_page_pairs_and_stacks_on_a_phone(page: Page, host_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    arm_page(page)
    page.goto(host_url, timeout=20_000, wait_until="domcontentloaded")
    form = page.get_by_test_id("pairing")
    expect(form).to_be_visible(timeout=20_000)
    expect(page.get_by_placeholder("https://host.example")).to_have_count(0)
    page.get_by_placeholder("XXXX-XXXX").fill(mint_pairing_code())
    page.get_by_role("button", name="Pair").click()
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    expect(page.get_by_test_id("phone-nav")).to_be_visible()
    page.get_by_test_id("phone-tab-chats").click()
    name = unique_bot("PhoneWin")
    create_named_bot(page, name)
    expect(page.get_by_test_id("thread-header")).to_contain_text(name, timeout=8_000)
    page.get_by_test_id("phone-tab-chats").click()
    expect(bot_row(page, name)).to_be_visible()
    page.get_by_test_id("phone-tab-desk").click()
    expect(page.get_by_test_id("new-memory")).to_be_visible(timeout=8_000)
