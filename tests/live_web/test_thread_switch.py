from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    bot_row,
    hold_thread_snapshot_gets,
    thread_header,
    unique_bot,
)
from tests.live_web.helpers import (
    create_named_bot_phone,
    open_phone_tab,
    pair_host_page,
    send_message_phone,
)

pytestmark = pytest.mark.live


def test_host_page_switch_shows_cached_thread_while_snapshot_waits(
    page: Page, host_url: str
) -> None:
    first = unique_bot("HoldWebA")
    second = unique_bot("HoldWebB")
    pair_host_page(page, host_url)
    create_named_bot_phone(page, first)
    send_message_phone(page, "stay visible")
    create_named_bot_phone(page, second)
    send_message_phone(page, "other chat")
    open_phone_tab(page, "chats")
    bot_row(page, first).click()
    expect(thread_header(page)).to_contain_text(first, timeout=8_000)
    open_phone_tab(page, "chat")
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(
            has_text="stay visible"
        )
    ).to_be_visible()
    open_phone_tab(page, "chats")
    bot_row(page, second).click()
    expect(thread_header(page)).to_contain_text(second, timeout=8_000)
    with hold_thread_snapshot_gets(page) as held:
        open_phone_tab(page, "chats")
        bot_row(page, first).click()
        expect(thread_header(page)).to_contain_text(first, timeout=8_000)
        open_phone_tab(page, "chat")
        expect(page.get_by_test_id("thread-loading")).to_have_count(0)
        expect(
            page.locator('[data-testid="thread-message"][data-role="user"]').filter(
                has_text="stay visible"
            )
        ).to_be_visible()
        expect(
            page.locator('[data-testid="thread-message"][data-role="user"]').filter(
                has_text="other chat"
            )
        ).to_have_count(0)
        assert held.wait(timeout=10), "snapshot GET was never held"
        expect(
            page.locator('[data-testid="thread-message"][data-role="user"]').filter(
                has_text="stay visible"
            )
        ).to_be_visible()
