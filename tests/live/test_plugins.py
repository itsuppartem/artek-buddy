from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import create_named_bot, pair_fresh, send_message, unique_bot

pytestmark = pytest.mark.live


def test_plugins_pane_key_connect_docs_then_chat_answers(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("PlugWin")
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_role("button", name="Plugins")).to_be_visible()
    page.get_by_test_id("open-plugins").click()
    pane = page.get_by_test_id("plugins-pane")
    expect(pane).to_be_visible()
    leftover = page.get_by_test_id("plugins-remove")
    if leftover.count() and leftover.first.is_visible():
        leftover.click()
        expect(page.get_by_text("Paste a key to connect apps.")).to_be_visible()
    expect(page.get_by_text("Plugins ship with a later stage.")).to_have_count(0)
    expect(page.get_by_text("Paste a key to connect apps.")).to_be_visible()
    key = page.get_by_label("Plugins key")
    key.fill("ak-test-secret-uiok")
    expect(key).to_have_value("ak-test-secret-uiok")
    page.get_by_test_id("plugins-save").click()
    expect(page.get_by_text("Key saved")).to_be_visible()
    search = page.get_by_label("Search apps")
    search.fill("docs")
    row = page.get_by_test_id("plugin-row-docs")
    expect(row).to_be_visible()
    row.get_by_role("button", name="Connect").click()
    expect(row.get_by_text("Connected")).to_be_visible()
    row.get_by_role("button", name="Disconnect").click()
    expect(row.get_by_role("button", name="Connect")).to_be_visible()
    row.get_by_role("button", name="Connect").click()
    expect(row.get_by_text("Connected")).to_be_visible()
    page.get_by_role("button", name="Close Plugins").click()
    create_named_bot(page, name)
    send_message(page, "please e2e-plugin-docs", name)
    expect(page.locator('[data-testid="thread-message"][data-role="bot"]')).to_contain_text(
        "Subotica", timeout=8_000
    )
    page.get_by_test_id("open-plugins").click()
    expect(page.get_by_test_id("plugins-pane")).to_be_visible()
    page.get_by_test_id("plugins-remove").click()
    expect(page.get_by_text("Paste a key to connect apps.")).to_be_visible()
