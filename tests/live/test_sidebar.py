from __future__ import annotations

import uuid

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import bot_row, create_named_bot, open_bot_menu, pair_fresh

pytestmark = pytest.mark.live


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _pair_ready(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)


def _archive_named(page: Page, name: str) -> None:
    open_bot_menu(page, name)
    page.get_by_role("menuitem", name="Archive").click()
    expect(bot_row(page, name)).to_have_count(0)


def test_plus_plugins_and_you_label(page: Page, client_url: str, host_url: str) -> None:
    _pair_ready(page, client_url, host_url)
    page.get_by_title("New bot").click()
    expect(page.get_by_placeholder("Name this bot")).to_be_visible()
    page.locator("button").filter(has_text="✕").last.click()
    expect(page.get_by_placeholder("Name this bot")).to_have_count(0)

    page.get_by_text("Plugins", exact=True).click()
    expect(page.get_by_text("Plugins ship with a later stage.")).to_be_visible()

    page.get_by_text("You", exact=True).click()
    expect(page.get_by_text("Bot Settings")).to_have_count(0)


def test_search_filters_and_click_opens_chat(page: Page, client_url: str, host_url: str) -> None:
    token = _uid()
    alpha = f"Alpha {token}"
    bravo = f"Bravo {token}"
    _pair_ready(page, client_url, host_url)
    create_named_bot(page, alpha, title=f"notes about cats {token}")
    create_named_bot(page, bravo, title="shipping desk")

    search = page.get_by_placeholder("Search")
    search.fill(alpha)
    expect(bot_row(page, alpha)).to_be_visible()
    expect(bot_row(page, bravo)).to_have_count(0)

    search.fill(f"cats {token}")
    expect(bot_row(page, alpha)).to_be_visible()
    expect(bot_row(page, bravo)).to_have_count(0)

    search.fill("zzz-no-match")
    expect(bot_row(page, alpha)).to_have_count(0)
    expect(bot_row(page, bravo)).to_have_count(0)

    search.fill("")
    expect(bot_row(page, alpha)).to_be_visible()
    expect(bot_row(page, bravo)).to_be_visible()
    bot_row(page, alpha).click()
    expect(page.locator('[data-testid="thread-pane"] button').filter(has_text=alpha)).to_be_visible()
    expect(bot_row(page, alpha).get_by_test_id("bot-preview")).to_contain_text(f"cats {token}")


def test_context_menu_pin_unread_edit_duplicate(page: Page, client_url: str, host_url: str) -> None:
    name = f"Menu { _uid() }"
    _pair_ready(page, client_url, host_url)
    create_named_bot(page, name)

    open_bot_menu(page, name)
    page.get_by_role("menuitem", name="Pin").click()
    expect(bot_row(page, name).get_by_title("Pinned")).to_be_visible()

    open_bot_menu(page, name)
    page.get_by_role("menuitem", name="Unpin").click()
    expect(bot_row(page, name).get_by_title("Pinned")).to_have_count(0)

    open_bot_menu(page, name)
    page.get_by_role("menuitem", name="Mark as Unread").click()
    expect(bot_row(page, name).get_by_test_id("unread-dot")).to_be_visible()

    open_bot_menu(page, name)
    page.get_by_role("menuitem", name="Mark as Read").click()
    expect(bot_row(page, name).get_by_test_id("unread-dot")).to_have_count(0)

    open_bot_menu(page, name)
    page.get_by_role("menuitem", name="Edit Profile").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible()

    open_bot_menu(page, name)
    page.get_by_role("menuitem", name="Duplicate").click()
    expect(bot_row(page, f"{name} (Copy)")).to_be_visible(timeout=20_000)


def test_archive_restore_and_empty_inbox(page: Page, client_url: str, host_url: str) -> None:
    token = _uid()
    first = f"Keep {token}"
    extra = f"Park {token}"
    _pair_ready(page, client_url, host_url)
    create_named_bot(page, first)
    create_named_bot(page, extra)

    for _ in range(20):
        if page.get_by_test_id("bot-row").count() == 0:
            break
        leftover = page.get_by_test_id("bot-row").first.get_attribute("data-bot-name")
        assert leftover
        _archive_named(page, leftover)
    else:
        raise AssertionError("inbox still had bot rows after 20 archives")

    expect(page.get_by_test_id("empty-inbox")).to_be_visible(timeout=20_000)
    page.get_by_role("button", name="Open archived").click()
    expect(page.get_by_test_id("archived-list")).to_be_visible()
    page.get_by_placeholder("Search").fill(first)
    row = page.locator('[data-testid="archived-bot-row"]').filter(has_text=first)
    expect(row).to_have_count(1)
    page.get_by_placeholder("Search").fill("zzz-no-match")
    expect(page.locator('[data-testid="archived-bot-row"]').filter(has_text=first)).to_have_count(0)
    page.get_by_placeholder("Search").fill("")
    row.get_by_test_id("restore-chat").click()
    expect(bot_row(page, first)).to_be_visible(timeout=20_000)
    if page.get_by_test_id("back-inbox").count():
        page.get_by_test_id("back-inbox").click()
    expect(bot_row(page, first)).to_be_visible()


def test_delete_cancel_keeps_bot(page: Page, client_url: str, host_url: str) -> None:
    name = f"KeepMe {_uid()}"
    _pair_ready(page, client_url, host_url)
    create_named_bot(page, name)
    page.locator('[data-testid="thread-pane"] button').filter(has_text=name).click()
    expect(page.get_by_text("Bot Settings")).to_be_visible()
    page.get_by_role("button", name="Delete chat…").click()
    page.get_by_role("button", name="Cancel").click()
    expect(bot_row(page, name)).to_be_visible()
    expect(page.get_by_text("Delete this chat and its history?")).to_have_count(0)

    open_bot_menu(page, name)
    page.get_by_role("menuitem", name="Delete").click()
    expect(bot_row(page, name)).to_have_count(0)
