from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import unique_bot
from tests.live_web.helpers import (
    create_named_bot_phone,
    ensure_model_phone,
    pair_host_page,
    send_message_phone,
)

pytestmark = [pytest.mark.live, pytest.mark.model, pytest.mark.timeout(400)]


def test_host_page_real_model_replies_on_iphone(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    ensure_model_phone(page)
    create_named_bot_phone(page, unique_bot("GrokWeb"))
    send_message_phone(page, "Reply with the single word pong and nothing else.")
    expect(page.locator("[data-testid=thread-message][data-role=bot]").last).to_be_visible(
        timeout=180_000
    )
    expect(page.get_by_test_id("typing-indicator")).to_have_count(0, timeout=180_000)
