from __future__ import annotations

import uuid

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    bot_row,
    composer,
    create_named_bot,
    hold_thread_snapshot_gets,
    open_bot_menu,
    open_chat,
    pair_fresh,
    send_message,
    thread_header,
    unique_bot,
)

pytestmark = pytest.mark.live


def test_sidebar_search_menu_archive_and_delete(page: Page, client_url: str, host_url: str) -> None:
    """One pair. The host keeps leftover bots from earlier ui tests; only touch ours."""
    token = uuid.uuid4().hex[:8]
    alpha = f"Alpha {token}"
    bravo = f"Bravo {token}"

    pair_fresh(page, client_url, host_url)

    page.get_by_role("button", name="New bot").click()
    expect(page.get_by_placeholder("Name this bot")).to_be_visible()

    page.get_by_test_id("open-plugins").click()
    expect(page.get_by_test_id("plugins-pane")).to_be_visible()
    page.get_by_role("button", name="Close Plugins").click()
    page.get_by_text("You", exact=True).click()
    expect(page.get_by_test_id("models-pane")).to_be_visible()
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
    page.get_by_role("menuitem", name="Mark as unread").click()
    expect(bot_row(page, alpha).get_by_test_id("unread-dot")).to_be_visible()
    open_bot_menu(page, alpha)
    page.get_by_role("menuitem", name="Mark as read").click()
    expect(bot_row(page, alpha).get_by_test_id("unread-dot")).to_have_count(0)
    open_bot_menu(page, alpha)
    page.get_by_role("menuitem", name="Edit profile").click()
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
    page.get_by_role("menuitem", name="Edit profile").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible()
    page.get_by_role("button", name="Delete chat…").click()
    page.get_by_role("button", name="Cancel").click()
    expect(bot_row(page, alpha)).to_have_count(1)
    open_bot_menu(page, alpha)
    page.get_by_role("menuitem", name="Delete").click()
    expect(bot_row(page, alpha)).to_have_count(0)


def test_switch_bots_keeps_header_and_thread(page: Page, client_url: str, host_url: str) -> None:
    first = unique_bot("KeepA")
    second = unique_bot("KeepB")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, first)
    send_message(page, "alpha line", first)
    create_named_bot(page, second)
    send_message(page, "bravo line", second)
    open_chat(page, first)
    expect(thread_header(page)).to_contain_text(first)
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(
            has_text="alpha line"
        )
    ).to_be_visible()
    open_chat(page, second)
    expect(thread_header(page)).to_contain_text(second)
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(
            has_text="bravo line"
        )
    ).to_be_visible()
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(
            has_text="alpha line"
        )
    ).to_have_count(0)
    open_chat(page, first)
    expect(thread_header(page)).to_contain_text(first)
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(
            has_text="alpha line"
        )
    ).to_be_visible()
    first_box = bot_row(page, first).bounding_box()
    second_box = bot_row(page, second).bounding_box()
    assert first_box is not None and second_box is not None
    assert first_box["y"] < second_box["y"]


def test_unread_mark_is_named_and_visible(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("Unread")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    open_bot_menu(page, name)
    page.get_by_role("menuitem", name="Mark as unread").click()
    row = bot_row(page, name)
    pin = row.get_by_test_id("unread-dot")
    expect(pin).to_be_visible()
    expect(pin).to_have_accessible_name("Unread")
    expect(row).to_have_accessible_name(f"Open chat {name} (unread)")


def test_inbox_search_marks_preview_hit(page: Page, client_url: str, host_url: str) -> None:
    token = uuid.uuid4().hex[:8]
    lead = unique_bot("Lead")
    other = unique_bot("Other")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, lead, title=f"notes about cats {token}")
    create_named_bot(page, other, title="shipping desk")
    search = page.get_by_placeholder("Search")
    search.fill(token)
    row = bot_row(page, lead)
    expect(row).to_have_count(1)
    expect(bot_row(page, other)).to_have_count(0)
    expect(row.get_by_test_id("inbox-hit")).to_have_text(token)
    expect(row.get_by_test_id("bot-preview")).to_contain_text(token)


def test_inbox_search_no_match_shows_empty_and_clear(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("Seek")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    expect(bot_row(page, name)).to_have_count(1)
    search = page.get_by_placeholder("Search")
    search.fill("zzz-no-match")
    expect(bot_row(page, name)).to_have_count(0)
    empty = page.get_by_test_id("inbox-search-empty")
    expect(empty).to_be_visible()
    expect(empty).to_contain_text("No chats match")
    expect(empty).to_contain_text("Clear Search")
    clearer = page.get_by_role("button", name="Clear Search")
    expect(clearer).to_be_visible()
    clearer.click()
    expect(search).to_have_value("")
    expect(empty).to_have_count(0)
    expect(bot_row(page, name)).to_have_count(1)


def test_switch_during_stream_keeps_chat(page: Page, client_url: str, host_url: str) -> None:
    first = unique_bot("LiveA")
    second = unique_bot("LiveB")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, first)
    create_named_bot(page, second)
    open_chat(page, first)
    box = composer(page)
    box.fill("please e2e-slow")
    expect(box).to_have_value("please e2e-slow")
    box.press("Enter")
    expect(page.get_by_test_id("typing-indicator")).to_be_visible(timeout=8_000)
    open_chat(page, second)
    expect(thread_header(page)).to_contain_text(second)
    open_chat(page, first)
    expect(thread_header(page)).to_contain_text(first)
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(
            has_text="please e2e-slow"
        )
    ).to_be_visible()


def test_switch_never_blanks_thread(page: Page, client_url: str, host_url: str) -> None:
    first = unique_bot("BlankA")
    second = unique_bot("BlankB")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, first)
    send_message(page, "stay visible", first)
    create_named_bot(page, second)
    send_message(page, "other chat", second)
    open_chat(page, first)
    expect(page.get_by_test_id("thread-composer")).to_be_visible()
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(
            has_text="stay visible"
        )
    ).to_be_visible()
    open_chat(page, second)
    expect(thread_header(page)).to_contain_text(second)
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(
            has_text="other chat"
        )
    ).to_be_visible()
    with hold_thread_snapshot_gets(page) as held:
        open_chat(page, first)
        expect(thread_header(page)).to_contain_text(first)
        expect(page.get_by_test_id("thread-composer")).to_be_visible()
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
    expect(page.get_by_test_id("empty-bots")).to_have_count(0)


def test_switch_keeps_loaded_earlier_page(page: Page, client_url: str, host_url: str) -> None:
    first = unique_bot("HistA")
    second = unique_bot("HistB")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, first)
    send_message(page, "please e2e-load-earlier", first)
    create_named_bot(page, second)
    send_message(page, "other chat", second)
    open_chat(page, first)
    earlier = page.get_by_test_id("load-earlier")
    expect(earlier).to_be_visible(timeout=15_000)
    earlier.click()
    expect(page.get_by_text("e2e-old-00", exact=True)).to_be_visible(timeout=15_000)
    open_chat(page, second)
    expect(thread_header(page)).to_contain_text(second)
    open_chat(page, first)
    expect(thread_header(page)).to_contain_text(first)
    expect(page.get_by_text("e2e-old-00", exact=True)).to_be_visible()


def test_uncached_chat_shows_loading_not_a_blank_thread(
    page: Page, client_url: str, host_url: str
) -> None:
    first = unique_bot("LoadA")
    extras = [unique_bot("LoadB"), unique_bot("LoadC"), unique_bot("LoadD")]
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, first)
    send_message(page, "stay visible", first)
    for name in extras:
        create_named_bot(page, name)
        open_chat(page, name)
    open_chat(page, extras[-1])
    expect(thread_header(page)).to_contain_text(extras[-1])
    with hold_thread_snapshot_gets(page) as held:
        open_chat(page, first)
        expect(thread_header(page)).to_contain_text(first)
        expect(page.get_by_test_id("thread-loading")).to_be_visible()
        expect(page.get_by_test_id("thread-loading")).to_contain_text("Loading this chat")
        expect(
            page.locator('[data-testid="thread-message"][data-role="user"]').filter(
                has_text="stay visible"
            )
        ).to_have_count(0)
        assert held.is_set() or held.wait(timeout=10), "snapshot GET was never held"
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(
            has_text="stay visible"
        )
    ).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("thread-loading")).to_have_count(0)


def test_inbox_row_click_opens_that_chat(page: Page, client_url: str, host_url: str) -> None:
    lead = unique_bot("Lead")
    research = unique_bot("Research")
    park = unique_bot("Park")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, lead)
    create_named_bot(page, research)
    create_named_bot(page, park)
    open_chat(page, research)
    expect(thread_header(page)).to_contain_text(research)
    bot_row(page, lead).click()
    expect(thread_header(page)).to_contain_text(lead)
    expect(bot_row(page, lead)).to_have_attribute("aria-current", "page")
    expect(composer(page)).to_be_visible()
    open_chat(page, park)
    expect(thread_header(page)).to_contain_text(park)
    bot_row(page, lead).click()
    expect(thread_header(page)).to_contain_text(lead)
    expect(bot_row(page, lead)).to_have_attribute("aria-current", "page")
    expect(thread_header(page)).not_to_contain_text(research)
    expect(thread_header(page)).not_to_contain_text(park)
