from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import unique_bot
from tests.live_web.helpers import create_named_bot_phone, pair_host_page, send_message_phone

pytestmark = pytest.mark.live


def test_host_page_does_not_read_this_pc(page: Page, host_url: str) -> None:
    owner_reads: list[str] = []

    def track(request) -> None:
        if "/local/owner-read" in request.url:
            owner_reads.append(request.url)

    page.on("request", track)
    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("ReadWeb"))
    send_message_phone(page, "e2e-consent-read")
    card = page.get_by_test_id("consent-card")
    expect(card).to_be_visible(timeout=20_000)
    page.get_by_test_id("ask-option").filter(has_text="Allow once").click()
    expect(card).to_have_attribute("data-status", "answered", timeout=20_000)
    assert owner_reads == []
