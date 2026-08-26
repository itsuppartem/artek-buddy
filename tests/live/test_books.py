from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    composer,
    create_named_bot,
    ensure_model,
    pair_fresh,
    send_message,
    unique_bot,
)

pytestmark = pytest.mark.live


def test_teach_playbook_in_chat_then_run_from_chip(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("BookWin")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    ensure_model(page)
    send_message(page, "please e2e-save-book", name)
    card = page.get_by_test_id("book-card")
    expect(card).to_contain_text("Invoice", timeout=8_000)
    expect(card).to_contain_text("please run Invoice")
    chip = page.get_by_test_id("book-ask-invoice")
    expect(chip).to_be_visible(timeout=8_000)
    chip.click()
    box = composer(page)
    expect(box).to_have_value("please run Invoice")
    box.press("Enter")
    opened = page.get_by_test_id("book-card").filter(has_text="Open the invoice site")
    expect(opened).to_be_visible(timeout=8_000)
    send_message(page, "please e2e-forget-book", name)
    expect(page.get_by_test_id("book-card").filter(has_text="Forgotten")).to_be_visible(
        timeout=8_000
    )
    expect(page.get_by_test_id("book-ask-invoice")).to_have_count(0)
