from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import unique_bot
from tests.live_web.helpers import create_named_bot_phone, pair_host_page, send_message_phone

pytestmark = pytest.mark.live


def test_host_page_scripted_reply_on_iphone(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("HelloWeb"))
    send_message_phone(page, "hello")
    expect(page.locator('[data-testid="thread-message"][data-role="bot"]').last).to_contain_text(
        "ok",
        timeout=20_000,
    )
