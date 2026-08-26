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
        page.get_by_label("Device name").fill(device_name)
    page.get_by_role("button", name="Pair").click()
    expect(page.get_by_test_id("phone-nav")).to_be_visible(timeout=20_000)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)


def open_phone_tab(page: Page, tab: str) -> None:
    page.get_by_test_id(f"phone-tab-{tab}").click()


def create_named_bot_phone(page: Page, name: str) -> None:
    open_phone_tab(page, "chats")
    expect(page.get_by_role("button", name="New bot")).to_be_visible(timeout=8_000)
    page.get_by_role("button", name="New bot").click()
    box = page.get_by_placeholder("Name this bot")
    expect(box).to_be_visible(timeout=10_000)
    box.fill(name)
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


def ensure_model_phone(page: Page) -> None:
    open_phone_tab(page, "chats")
    ensure_model(page)
