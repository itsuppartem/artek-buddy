from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    create_named_bot,
    fulfill_json,
    open_memory,
    open_settings,
    pair_fresh,
    unique_bot,
)

pytestmark = pytest.mark.live


def test_settings_save_shows_saved(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("SavSet")
    renamed = f"{name} Ok"
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    open_settings(page, name)
    page.get_by_role("button", name="Edit profile").click()
    page.get_by_test_id("bot-name-input").fill(renamed)
    page.get_by_test_id("settings-save").click()
    expect(page.get_by_role("button", name="Saved")).to_be_visible(timeout=8_000)
    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    open_settings(page, renamed)
    expect(page.get_by_test_id("bot-settings-name")).to_have_text(renamed)


def test_memory_save_shows_saved(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("SavMem")
    note = f"Keep {name}"
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    open_memory(page, name)
    page.get_by_test_id("new-memory").click()
    facts = page.get_by_placeholder("Facts to remember")
    facts.fill(note)
    page.get_by_test_id("memory-save").click()
    expect(page.get_by_test_id("memory-save")).to_have_text("Saved", timeout=8_000)
    expect(page.get_by_test_id("memory-doc").filter(has_text=note)).to_be_visible(timeout=8_000)
    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    open_memory(page, name)
    expect(page.get_by_test_id("memory-doc").filter(has_text=note)).to_be_visible(timeout=8_000)


def test_settings_save_error_keeps_save(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("SavFail")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    open_settings(page, name)
    page.get_by_role("button", name="Edit profile").click()
    fulfill_json(page, "**/v1/bots/**", 500, '{"detail":"host down"}', method="PATCH")
    page.get_by_test_id("bot-name-input").fill(f"{name} No")
    page.get_by_test_id("settings-save").click()
    expect(page.get_by_test_id("settings-save-error")).to_contain_text("host down", timeout=8_000)
    expect(page.get_by_role("button", name="Saved")).to_have_count(0)
    expect(page.get_by_test_id("settings-save")).to_have_text("Save")
    expect(page.get_by_text("host down")).to_have_count(1)
