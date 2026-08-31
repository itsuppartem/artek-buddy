from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import unique_bot
from tests.live_web.helpers import (
    create_named_bot_phone,
    pair_host_page,
    send_message_phone,
)

pytestmark = pytest.mark.live


def test_host_page_skill_book_stays_internal_to_the_agent(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("BookWeb"))
    send_message_phone(page, "please e2e-install-book")
    consent = page.get_by_test_id("consent-card")
    expect(consent).to_be_visible(timeout=8_000)
    page.get_by_role("button", name="B Always", exact=True).click()
    thread = page.get_by_test_id("thread")
    expect(thread.get_by_text("I'll keep that skill.", exact=True)).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("book-card")).to_have_count(0)
    expect(page.get_by_test_id("book-ask-invoice")).to_have_count(0)

    send_message_phone(page, "please e2e-run-book")
    expect(thread.get_by_text("Following Invoice.", exact=True)).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("book-card")).to_have_count(0)
    expect(page.get_by_test_id("book-ask-invoice")).to_have_count(0)
    expect(page.get_by_text("run failed: run-")).to_have_count(0)


def test_host_page_fail_raw_id_is_human(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("FailWeb"))
    send_message_phone(page, "please e2e-fail-raw now")
    expect(page.get_by_test_id("run-error")).to_be_visible(timeout=20_000)
    expect(page.get_by_test_id("run-error")).to_contain_text("The turn failed.")
    expect(page.get_by_text("run failed: run-fb7fd73f-32ed-43ed-a22f-a561aab1600a")).to_have_count(
        0
    )
    expect(page.get_by_test_id("run-error")).not_to_contain_text("run failed: run-")
