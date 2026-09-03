from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    arm_page,
    bot_row,
    composer,
    fulfill_json,
    thread_header,
    unique_bot,
)
from tests.live_web.helpers import (
    create_named_bot_phone,
    expect_bot_in_chats,
    open_phone_tab,
    pair_host_page,
)

pytestmark = pytest.mark.live


def test_host_page_pairing_copy_has_no_token_or_module(page: Page, host_url: str) -> None:
    arm_page(page)
    page.goto(host_url, timeout=20_000, wait_until="domcontentloaded")
    form = page.get_by_test_id("pairing")
    expect(form).to_be_visible(timeout=20_000)
    expect(form.get_by_text("Pair this phone")).to_be_visible()
    expect(form).to_contain_text("On the Pi, create a pairing code. Type it here, then Pair.")
    expect(form).not_to_contain_text("token")
    expect(form).not_to_contain_text("mint")
    expect(form).not_to_contain_text("python -m")
    expect(page.get_by_test_id("pairing-host-command")).to_have_count(0)
    expect(page.get_by_placeholder("https://host.example")).to_have_count(0)
    expect(page.get_by_role("button", name="Pair")).to_be_disabled()


def test_host_page_pairs_and_stacks_on_iphone_11_pro(page: Page, host_url: str) -> None:
    box = page.viewport_size
    assert box == {"width": 375, "height": 812}
    pair_host_page(page, host_url)
    expect(page.get_by_test_id("phone-desk-pad")).to_have_count(0)
    name = unique_bot("PhoneWin")
    create_named_bot_phone(page, name)
    expect(page.get_by_test_id("thread-header")).to_contain_text(name, timeout=8_000)
    expect_bot_in_chats(page, name)
    open_phone_tab(page, "desk")
    expect(page.get_by_test_id("new-memory")).to_be_visible(timeout=8_000)
    page.get_by_title("Close panel").click()
    expect(page.get_by_test_id("phone-tab-chat")).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("thread-header")).to_contain_text(name)


def test_host_page_home_screen_hint_leaves_models_tappable(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    expect(page.get_by_test_id("home-screen-hint")).to_be_visible()
    open_phone_tab(page, "chats")
    expect(page.get_by_test_id("home-screen-hint")).to_be_visible()
    page.get_by_test_id("open-models").click()
    expect(page.get_by_test_id("models-pane")).to_be_visible(timeout=8_000)


def test_phone_computer_open_close_returns_to_chat(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    name = unique_bot("DeskBack")
    create_named_bot_phone(page, name)
    expect(page.get_by_test_id("phone-tab-chat")).to_have_attribute("aria-current", "page")
    page.get_by_role("button", name="Computer").click()
    expect(page.get_by_test_id("phone-tab-desk")).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("computer-state")).to_be_visible(timeout=8_000)
    page.get_by_title("Close panel").click()
    expect(page.get_by_test_id("phone-tab-chat")).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("thread-header")).to_contain_text(name)
    expect(page.get_by_test_id("thread-pane")).to_be_visible()
    expect(page.get_by_test_id("computer-state")).to_have_count(0)


def test_phone_models_plugins_close_returns_to_chat(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    name = unique_bot("HatchBack")
    create_named_bot_phone(page, name)
    open_phone_tab(page, "chats")
    page.get_by_test_id("open-models").click()
    expect(page.get_by_test_id("models-pane")).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("phone-tab-desk")).to_have_attribute("aria-current", "page")
    page.get_by_role("button", name="Close Models").click()
    expect(page.get_by_test_id("phone-tab-chat")).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("thread-header")).to_contain_text(name)
    expect(page.get_by_test_id("models-pane")).to_have_count(0)

    open_phone_tab(page, "chats")
    page.get_by_test_id("open-plugins").click()
    expect(page.get_by_test_id("plugins-pane")).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("phone-tab-desk")).to_have_attribute("aria-current", "page")
    page.get_by_role("button", name="Close Plugins").click()
    expect(page.get_by_test_id("phone-tab-chat")).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("thread-header")).to_contain_text(name)
    expect(page.get_by_test_id("plugins-pane")).to_have_count(0)
    expect(page.get_by_test_id("thread-pane")).to_be_visible()


def test_host_page_auth_error_says_pair_this_phone_again(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    fulfill_json(page, "**/v1/**", 401, '{"detail":"invalid token"}')
    page.reload()
    card = page.get_by_test_id("auth-error")
    expect(card).to_be_visible(timeout=20_000)
    expect(card.get_by_role("button", name="Pair this computer again")).to_have_count(0)
    card.get_by_role("button", name="Pair this phone again").click()
    expect(page.get_by_test_id("pairing")).to_be_visible(timeout=20_000)
    expect(page.get_by_text("Pair this phone")).to_be_visible()
    expect(page.get_by_placeholder("https://host.example")).to_have_count(0)


def test_host_page_workspace_events_auth_says_pair_this_phone_again(
    page: Page, host_url: str
) -> None:
    pair_host_page(page, host_url)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    fulfill_json(page, "**/v1/events", 401, '{"detail":"invalid token"}')
    page.reload()
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    expect(page.get_by_test_id("auth-error")).to_be_visible(timeout=20_000)
    expect(page.get_by_role("button", name="Pair this computer again")).to_have_count(0)
    expect(page.get_by_test_id("pairing")).to_have_count(0)
    page.get_by_role("button", name="Pair this phone again").click()
    expect(page.get_by_test_id("pairing")).to_be_visible(timeout=20_000)
    expect(page.get_by_text("Pair this phone")).to_be_visible()


def test_host_page_unsent_draft_stays_on_the_chat_it_was_typed_in(
    page: Page, host_url: str
) -> None:
    first = unique_bot("DraftWebA")
    second = unique_bot("DraftWebB")
    pair_host_page(page, host_url)
    create_named_bot_phone(page, first)
    create_named_bot_phone(page, second)
    open_phone_tab(page, "chats")
    bot_row(page, first).click()
    expect(thread_header(page)).to_contain_text(first, timeout=8_000)
    open_phone_tab(page, "chat")
    box = composer(page)
    box.fill("keep on A")
    expect(box).to_have_value("keep on A")
    open_phone_tab(page, "chats")
    bot_row(page, second).click()
    expect(thread_header(page)).to_contain_text(second, timeout=8_000)
    open_phone_tab(page, "chat")
    expect(composer(page)).to_have_value("")
    open_phone_tab(page, "chats")
    bot_row(page, first).click()
    expect(thread_header(page)).to_contain_text(first, timeout=8_000)
    open_phone_tab(page, "chat")
    expect(composer(page)).to_have_value("keep on A")
