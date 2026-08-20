from __future__ import annotations

import uuid

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import bot_row, create_named_bot, open_bot_menu, pair_fresh, thread_header

pytestmark = pytest.mark.live


def test_sidebar_search_menu_archive_and_delete(page: Page, client_url: str, host_url: str) -> None:
    """One pair. The host keeps leftover bots from earlier ui tests; only touch ours."""
    token = uuid.uuid4().hex[:8]
    alpha = f"Alpha {token}"
    bravo = f"Bravo {token}"

    pair_fresh(page, client_url, host_url)

    page.get_by_title("New bot").click()
    expect(page.get_by_placeholder("Name this bot")).to_be_visible()

    page.get_by_text("Plugins", exact=True).click()
    expect(page.get_by_text("Plugins ship with a later stage.")).to_be_visible()
    page.get_by_text("You", exact=True).click()
    expect(page.get_by_text("Bot Settings")).to_have_count(0)

    create_named_bot(page, alpha, title=f"notes about cats {token}")
    expect(bot_row(page, alpha)).to_contain_text(f"notes about cats {token}")
    create_named_bot(page, bravo, title="shipping desk")

    expect(bot_row(page, alpha).get_by_test_id("bot-avatar")).to_be_visible()
    expect(bot_row(page, alpha).locator('img[src="/bot-mark.png"]')).to_have_count(1)

    search = page.get_by_placeholder("Search")
    search.fill(alpha)
    expect(bot_row(page, alpha)).to_have_count(1)
    expect(bot_row(page, bravo)).to_have_count(0)
    search.fill(f"cats {token}")
    expect(bot_row(page, alpha)).to_have_count(1)
    expect(bot_row(page, bravo)).to_have_count(0)
    search.fill("zzz-no-match")
    expect(bot_row(page, alpha)).to_have_count(0)
    search.fill("")
    expect(bot_row(page, alpha)).to_have_count(1)
    expect(bot_row(page, bravo)).to_have_count(1)
    bot_row(page, alpha).click()
    expect(thread_header(page)).to_contain_text(alpha)

    open_bot_menu(page, alpha)
    page.get_by_role("menuitem", name="Pin").click()
    expect(bot_row(page, alpha).get_by_title("Pinned")).to_be_visible(timeout=8_000)
    open_bot_menu(page, alpha)
    page.get_by_role("menuitem", name="Unpin").click()
    expect(bot_row(page, alpha).get_by_title("Pinned")).to_have_count(0)
    open_bot_menu(page, alpha)
    page.get_by_role("menuitem", name="Mark as Unread").click()
    expect(bot_row(page, alpha).get_by_test_id("unread-dot")).to_be_visible()
    open_bot_menu(page, alpha)
    page.get_by_role("menuitem", name="Mark as Read").click()
    expect(bot_row(page, alpha).get_by_test_id("unread-dot")).to_have_count(0)
    open_bot_menu(page, alpha)
    page.get_by_role("menuitem", name="Edit Profile").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible()
    open_bot_menu(page, alpha)
    page.get_by_role("menuitem", name="Duplicate").click()
    expect(bot_row(page, f"{alpha} (Copy)")).to_have_count(1, timeout=20_000)

    open_bot_menu(page, bravo)
    page.get_by_role("menuitem", name="Archive").click()
    expect(bot_row(page, bravo)).to_have_count(0)
    page.get_by_test_id("open-archived").click()
    expect(page.get_by_test_id("archived-list")).to_be_visible()
    search.fill(bravo)
    archived = page.locator('[data-testid="archived-bot-row"]').filter(has_text=bravo)
    expect(archived).to_have_count(1)
    search.fill("zzz-no-match")
    expect(page.locator('[data-testid="archived-bot-row"]').filter(has_text=bravo)).to_have_count(0)
    search.fill("")
    archived.get_by_test_id("restore-chat").click()
    expect(bot_row(page, bravo)).to_have_count(1, timeout=20_000)

    # restore() navigates to Bravo. Open Alpha settings from the row menu.
    bot_row(page, alpha).click()
    open_bot_menu(page, alpha)
    page.get_by_role("menuitem", name="Edit Profile").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible()
    page.get_by_role("button", name="Delete chat…").click()
    page.get_by_role("button", name="Cancel").click()
    expect(bot_row(page, alpha)).to_have_count(1)
    open_bot_menu(page, alpha)
    page.get_by_role("menuitem", name="Delete").click()
    expect(bot_row(page, alpha)).to_have_count(0)
