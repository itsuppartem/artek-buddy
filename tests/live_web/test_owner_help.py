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


def test_host_page_owner_answer_continues_the_parked_turn(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("OwnerHelpWeb"))
    send_message_phone(page, "please e2e-blocked-browser")

    card = page.get_by_test_id("ask-card")
    expect(card).to_be_visible(timeout=15_000)
    card.get_by_test_id("ask-option").filter(has_text="I completed the step").click()

    expect(card).to_contain_text("Answered: I completed the step", timeout=8_000)
    expect(
        page.get_by_test_id("thread").get_by_text("I continued after your help.", exact=True)
    ).to_be_visible(timeout=8_000)
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(
            has_text="I completed the step"
        )
    ).to_have_count(0)
