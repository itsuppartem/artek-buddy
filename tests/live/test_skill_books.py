from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    create_named_bot,
    ensure_model,
    pair_fresh,
    send_message,
    unique_bot,
)

pytestmark = pytest.mark.live


def test_skill_book_stays_internal_to_the_agent(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("BookWin")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    ensure_model(page)
    send_message(page, "please e2e-install-book", name)
    consent = page.get_by_test_id("consent-card")
    expect(consent).to_be_visible(timeout=8_000)
    page.get_by_role("button", name="B Always", exact=True).click()
    thread = page.get_by_test_id("thread")
    expect(thread.get_by_text("I'll keep that skill.", exact=True)).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("book-card")).to_have_count(0)
    expect(page.get_by_test_id("book-ask-invoice")).to_have_count(0)

    send_message(page, "please e2e-run-book", name)
    expect(thread.get_by_text("Following Invoice.", exact=True)).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("book-card")).to_have_count(0)
    expect(page.get_by_test_id("book-ask-invoice")).to_have_count(0)
    expect(page.get_by_text("run failed: run-")).to_have_count(0)

    send_message(page, "please e2e-forget-book", name)
    expect(thread.get_by_text("Forgotten.", exact=True)).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("book-card")).to_have_count(0)
    expect(page.get_by_test_id("book-ask-invoice")).to_have_count(0)
