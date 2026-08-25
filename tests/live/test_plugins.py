from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    composer,
    create_named_bot,
    ensure_model,
    fulfill_json,
    pair_fresh,
    restore_host,
    unique_bot,
)

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
    save = page.get_by_test_id("plugins-save")
    expect(save).to_be_enabled()
    save.click()
    expect(page.get_by_test_id("plugins-error")).to_contain_text("Paste a key first")
    fulfill_json(page, "**/v1/connections/key", 404, '{"detail":"Not Found"}', method="POST")
    key = page.get_by_label("Plugins key")
    key.fill("ak-test-secret-fail")
    expect(key).to_have_value("ak-test-secret-fail")
    save.click()
    expect(page.get_by_test_id("plugins-error")).to_contain_text("Not Found")
    restore_host(page)
    key.fill("ak-test-secret-uiok")
    expect(key).to_have_value("ak-test-secret-uiok")
    save.click()
    expect(page.get_by_test_id("plugins-key-saved")).to_contain_text("Key saved")
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
    ensure_model(page)
    chip = page.get_by_test_id("plugin-ask-docs")
    expect(chip).to_be_visible()
    chip.click()
    box = composer(page)
    expect(box).to_have_value("please use Docs")
    box.press("Enter")
    card = page.get_by_test_id("plugin-card")
    expect(card).to_contain_text("Docs", timeout=8_000)
    expect(card).to_contain_text("Subotica")
    page.get_by_test_id("open-plugins").click()
    expect(page.get_by_test_id("plugins-pane")).to_be_visible()
    page.get_by_test_id("plugins-remove").click()
    expect(page.get_by_text("Paste a key to connect apps.")).to_be_visible()
    page.get_by_role("button", name="Close Plugins").click()
    expect(page.get_by_test_id("plugin-ask-docs")).to_have_count(0)
