from __future__ import annotations

from playwright.sync_api import Page, expect
from tests.live.helpers import (
    arm_page,
    bot_row,
    composer,
    ensure_model,
    mint_pairing_code,
)


def pair_host_page(page: Page, host_url: str, device_name: str | None = None) -> None:
    arm_page(page)
    page.goto(host_url, timeout=20_000, wait_until="domcontentloaded")
    form = page.get_by_test_id("pairing")
    expect(form).to_be_visible(timeout=20_000)
    expect(page.get_by_placeholder("https://host.example")).to_have_count(0)
    expect(page.get_by_test_id("home-screen-hint")).to_be_visible()
    page.get_by_placeholder("XXXX-XXXX").fill(mint_pairing_code())
    if device_name is not None:
        form.get_by_text("Pairing options", exact=True).click()
        page.get_by_label("Device name").fill(device_name)
    page.get_by_role("button", name="Pair").click()
    expect(page.get_by_test_id("phone-nav")).to_be_visible(timeout=20_000)
    expect(page.get_by_test_id("today-view")).to_be_visible(timeout=20_000)


def open_phone_tab(page: Page, tab: str) -> None:
    if tab == "chat":
        if page.get_by_test_id("thread-pane").is_visible(timeout=0):
            return
        page.get_by_test_id("phone-tab-chats").click()
        current = page.locator('[data-testid="bot-row"][aria-current="page"]')
        target = current if current.count() else page.get_by_test_id("bot-row").first
        target.click()
        expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=8_000)
        return
    page.get_by_test_id(f"phone-tab-{tab}").click()


def open_settings_phone(page: Page) -> None:
    open_phone_tab(page, "more")
    expect(page.get_by_test_id("library-pane")).to_be_visible(timeout=8_000)
    page.get_by_test_id("library-open-settings").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible(timeout=8_000)


def open_memory_phone(page: Page) -> None:
    open_phone_tab(page, "more")
    expect(page.get_by_test_id("library-pane")).to_be_visible(timeout=8_000)
    page.get_by_test_id("library-open-memory").click()
    expect(page.get_by_role("heading", name="Memory")).to_be_visible(timeout=8_000)


def create_named_bot_phone(page: Page, name: str, *, private: bool | None = None) -> None:
    open_phone_tab(page, "chats")
    expect(page.get_by_role("button", name="New bot")).to_be_visible(timeout=8_000)
    page.get_by_role("button", name="New bot").click()
    box = page.get_by_placeholder("Name this bot")
    expect(box).to_be_visible(timeout=10_000)
    box.fill(name)
    if private is True:
        page.get_by_test_id("computer-mode-private").click()
    elif private is False:
        page.get_by_test_id("computer-mode-team").click()
    page.get_by_role("button", name="Create", exact=True).click()
    expect(page.get_by_placeholder("Name this bot")).to_have_count(0, timeout=20_000)
    expect(page.get_by_test_id("thread-header")).to_contain_text(name, timeout=8_000)


def send_message_phone(page: Page, text: str) -> None:
    ensure_model_phone(page)
    open_phone_tab(page, "chat")
    box = composer(page)
    expect(box).to_be_enabled(timeout=8_000)
    box.fill(text)
    expect(box).to_have_value(text)
    box.press("Enter")
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(has_text=text)
    ).to_be_visible(timeout=8_000)


def expect_bot_in_chats(page: Page, name: str) -> None:
    open_phone_tab(page, "chats")
    expect(bot_row(page, name)).to_be_visible(timeout=8_000)
    search = page.get_by_label("Search inbox").bounding_box()
    scroll = page.locator('[data-shell="rack"] > .ab-scroll').bounding_box()
    nav = page.get_by_test_id("phone-nav").bounding_box()
    assert search is not None
    assert scroll is not None
    assert nav is not None
    assert search["y"] < scroll["y"]
    assert scroll["height"] >= 40
    assert scroll["y"] + scroll["height"] <= nav["y"] + 2


def ensure_model_phone(page: Page) -> None:
    open_phone_tab(page, "more")
    expect(page.get_by_test_id("library-pane")).to_be_visible(timeout=8_000)
    ensure_model(page)
    open_phone_tab(page, "chats")
