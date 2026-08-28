from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import fulfill_json, unique_bot
from tests.live_web.helpers import create_named_bot_phone, open_phone_tab, pair_host_page

pytestmark = pytest.mark.live


def test_settings_save_shows_saved(page: Page, host_url: str) -> None:
    name = unique_bot("PhSavSet")
    renamed = f"{name} Ok"
    pair_host_page(page, host_url)
    create_named_bot_phone(page, name)
    page.get_by_test_id("thread-pane").get_by_role("button", name="Settings").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible(timeout=8_000)
    page.get_by_role("button", name="Edit profile").click()
    page.get_by_test_id("bot-name-input").fill(renamed)
    page.get_by_test_id("settings-save").click()
    expect(page.get_by_role("button", name="Saved")).to_be_visible(timeout=8_000)
    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_test_id("phone-nav")).to_be_visible(timeout=20_000)
    open_phone_tab(page, "chat")
    expect(page.get_by_test_id("thread-header")).to_contain_text(renamed, timeout=8_000)
    page.get_by_test_id("thread-pane").get_by_role("button", name="Settings").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("bot-settings-name")).to_have_text(renamed)


def test_memory_save_shows_saved(page: Page, host_url: str) -> None:
    name = unique_bot("PhSavMem")
    note = f"Keep {name}"
    pair_host_page(page, host_url)
    create_named_bot_phone(page, name)
    page.get_by_role("button", name="Computer").click()
    expect(page.get_by_test_id("new-memory")).to_be_visible(timeout=8_000)
    page.get_by_test_id("new-memory").click()
    page.get_by_placeholder("Facts to remember").fill(note)
    page.get_by_test_id("memory-save").click()
    expect(page.get_by_test_id("memory-save")).to_have_text("Saved", timeout=8_000)
    expect(page.get_by_test_id("memory-doc").filter(has_text=note)).to_be_visible(timeout=8_000)
    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_test_id("phone-nav")).to_be_visible(timeout=20_000)
    open_phone_tab(page, "chat")
    page.get_by_role("button", name="Computer").click()
    expect(page.get_by_test_id("memory-doc").filter(has_text=note)).to_be_visible(timeout=8_000)


def test_settings_save_error_keeps_save(page: Page, host_url: str) -> None:
    name = unique_bot("PhSavFail")
    pair_host_page(page, host_url)
    create_named_bot_phone(page, name)
    page.get_by_test_id("thread-pane").get_by_role("button", name="Settings").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible(timeout=8_000)
    page.get_by_role("button", name="Edit profile").click()
    fulfill_json(page, "**/v1/bots/**", 500, '{"detail":"host down"}', method="PATCH")
    page.get_by_test_id("bot-name-input").fill(f"{name} No")
    page.get_by_test_id("settings-save").click()
    expect(page.get_by_test_id("settings-save-error")).to_contain_text("host down", timeout=8_000)
    expect(page.get_by_role("button", name="Saved")).to_have_count(0)
    expect(page.get_by_test_id("settings-save")).to_have_text("Save")
    expect(page.get_by_text("host down")).to_have_count(1)
