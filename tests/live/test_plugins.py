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


def _plugins_ready(page: Page) -> None:
    pane = page.get_by_test_id("plugins-pane")
    expect(pane).to_be_visible()
    expect(pane).to_have_attribute("data-plugins-ready", "1", timeout=8_000)


def _plugins_key_form(page: Page) -> None:
    _plugins_ready(page)
    saved = page.get_by_test_id("plugins-key-saved")
    if saved.count() and saved.is_visible():
        page.get_by_test_id("plugins-remove").click()
        expect(page.get_by_text("Paste a key to connect apps.")).to_be_visible()
    expect(page.get_by_label("Plugins key")).to_be_visible()


def test_plugins_pane_key_connect_docs_then_chat_answers(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("PlugWin")
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_role("button", name="Plugins")).to_be_visible()
    page.get_by_test_id("open-plugins").click()
    _plugins_ready(page)
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


def test_plugin_login_link_opens_owner_browser(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("PlugLogin")
    pair_fresh(page, client_url, host_url)
    page.get_by_test_id("open-plugins").click()
    _plugins_ready(page)
    leftover = page.get_by_test_id("plugins-remove")
    if leftover.count() and leftover.first.is_visible():
        leftover.click()
        expect(page.get_by_text("Paste a key to connect apps.")).to_be_visible()
    page.get_by_label("Plugins key").fill("ak-test-secret-login")
    page.get_by_test_id("plugins-save").click()
    expect(page.get_by_test_id("plugins-key-saved")).to_contain_text("Key saved")
    page.get_by_role("button", name="Close Plugins").click()
    create_named_bot(page, name)
    ensure_model(page)
    page.context.route(
        "https://example.test/**",
        lambda route: route.fulfill(status=200, content_type="text/html", body="login"),
    )
    box = composer(page)
    box.fill("please e2e-connect-mail")
    expect(box).to_have_value("please e2e-connect-mail")
    box.press("Enter")
    card = page.get_by_test_id("plugin-card")
    expect(card).to_contain_text("Mail", timeout=8_000)
    link = page.get_by_test_id("plugin-connect-open")
    expect(link).to_have_attribute("href", "https://example.test/authorize?app=mail")
    with page.expect_popup() as opened:
        link.click()
    expect(opened.value).to_have_url("https://example.test/authorize?app=mail")
    opened.value.close()
    page.get_by_test_id("open-plugins").click()
    expect(page.get_by_test_id("plugins-pane")).to_be_visible()
    page.get_by_test_id("plugins-remove").click()
    expect(page.get_by_text("Paste a key to connect apps.")).to_be_visible()
    page.get_by_role("button", name="Close Plugins").click()


def test_chat_connects_docs_without_pane_click(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("PlugChat")
    pair_fresh(page, client_url, host_url)
    page.get_by_test_id("open-plugins").click()
    _plugins_ready(page)
    leftover = page.get_by_test_id("plugins-remove")
    if leftover.count() and leftover.first.is_visible():
        leftover.click()
        expect(page.get_by_text("Paste a key to connect apps.")).to_be_visible()
    page.get_by_label("Plugins key").fill("ak-test-secret-chat")
    page.get_by_test_id("plugins-save").click()
    expect(page.get_by_test_id("plugins-key-saved")).to_contain_text("Key saved")
    page.get_by_role("button", name="Close Plugins").click()
    create_named_bot(page, name)
    ensure_model(page)
    expect(page.get_by_test_id("plugin-ask-docs")).to_have_count(0)
    box = composer(page)
    box.fill("please e2e-connect-docs")
    box.press("Enter")
    card = page.get_by_test_id("plugin-card")
    expect(card).to_contain_text("Docs", timeout=8_000)
    expect(card).to_contain_text("Connected")
    expect(page.get_by_test_id("plugin-ask-docs")).to_be_visible(timeout=8_000)
    page.get_by_test_id("open-plugins").click()
    expect(page.get_by_test_id("plugins-pane")).to_be_visible()
    page.get_by_test_id("plugins-remove").click()
    expect(page.get_by_text("Paste a key to connect apps.")).to_be_visible()
    page.get_by_role("button", name="Close Plugins").click()
    expect(page.get_by_test_id("plugin-ask-docs")).to_have_count(0)


def test_plugins_connect_explains_when_start_fails(
    page: Page, client_url: str, host_url: str
) -> None:
    pair_fresh(page, client_url, host_url)
    page.get_by_test_id("open-plugins").click()
    _plugins_key_form(page)
    key = page.get_by_label("Plugins key")
    key.fill("ak-test-secret-setup")
    expect(key).to_have_value("ak-test-secret-setup")
    page.get_by_test_id("plugins-save").click()
    expect(page.get_by_test_id("plugins-key-saved")).to_contain_text("Key saved")
    page.get_by_label("Search apps").fill("needssetup")
    row = page.get_by_test_id("plugin-row-needssetup")
    expect(row).to_be_visible()
    row.get_by_role("button", name="Connect").click()
    error = page.get_by_test_id("plugins-error")
    expect(error).to_contain_text("could not start that connection", timeout=8_000)
    expect(error).to_contain_text("finish that setup")
    expect(error).to_contain_text("try Connect again")
    expect(row.get_by_role("button", name="Connect")).to_be_visible()


def test_plugin_chip_remove_does_not_send(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("PlugChip")
    pair_fresh(page, client_url, host_url)
    page.get_by_test_id("open-plugins").click()
    _plugins_key_form(page)
    page.get_by_label("Plugins key").fill("ak-test-secret-chip")
    page.get_by_test_id("plugins-save").click()
    expect(page.get_by_test_id("plugins-key-saved")).to_contain_text("Key saved")
    search = page.get_by_label("Search apps")
    search.fill("docs")
    row = page.get_by_test_id("plugin-row-docs")
    expect(row).to_be_visible()
    row.get_by_role("button", name="Connect").click()
    expect(row.get_by_text("Connected")).to_be_visible()
    page.get_by_role("button", name="Close Plugins").click()
    create_named_bot(page, name)
    ensure_model(page)
    chip = page.get_by_test_id("plugin-ask-docs")
    expect(chip).to_be_visible()
    expect(page.get_by_role("button", name="Remove Docs")).to_be_visible()
    page.get_by_role("button", name="Remove Docs").click()
    expect(chip).to_have_count(0)
    expect(composer(page)).to_have_value("")
    expect(page.get_by_test_id("plugin-card")).to_have_count(0)
    page.get_by_test_id("open-plugins").click()
    expect(page.get_by_test_id("plugins-pane")).to_be_visible()
    page.get_by_test_id("plugins-remove").click()
    expect(page.get_by_text("Paste a key to connect apps.")).to_be_visible()
    page.get_by_role("button", name="Close Plugins").click()


def test_plugin_connect_does_not_send_please_use(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("PlugNoSend")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    ensure_model(page)
    page.get_by_test_id("open-plugins").click()
    _plugins_key_form(page)
    page.get_by_label("Plugins key").fill("ak-test-secret-nosend")
    page.get_by_test_id("plugins-save").click()
    expect(page.get_by_test_id("plugins-key-saved")).to_contain_text("Key saved")
    page.get_by_label("Search apps").fill("docs")
    row = page.get_by_test_id("plugin-row-docs")
    expect(row).to_be_visible()
    row.get_by_role("button", name="Connect").click()
    expect(row.get_by_text("Connected")).to_be_visible()
    expect(page.locator('[data-testid="thread-message"][data-role="user"]')).to_have_count(0)
    expect(composer(page)).to_have_value("")
    page.get_by_role("button", name="Close Plugins").click()
    chip = page.get_by_test_id("plugin-ask-docs")
    expect(chip).to_be_visible()
    chip.click()
    expect(composer(page)).to_have_value("please use Docs")
    expect(page.locator('[data-testid="thread-message"][data-role="user"]')).to_have_count(0)
    page.get_by_test_id("open-plugins").click()
    expect(page.get_by_test_id("plugins-pane")).to_be_visible()
    page.get_by_test_id("plugins-remove").click()
    expect(page.get_by_text("Paste a key to connect apps.")).to_be_visible()
    page.get_by_role("button", name="Close Plugins").click()


def test_plugins_search_keeps_pane_open(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    page.get_by_test_id("open-plugins").click()
    _plugins_key_form(page)
    page.get_by_label("Plugins key").fill("ak-test-secret-search-open")
    page.get_by_test_id("plugins-save").click()
    expect(page.get_by_test_id("plugins-key-saved")).to_contain_text("Key saved")
    mail = page.get_by_test_id("plugin-row-mail")
    docs = page.get_by_test_id("plugin-row-docs")
    expect(mail).to_be_visible()
    expect(docs).to_be_visible()
    search = page.get_by_label("Search apps")
    search.fill("docs")
    expect(search).to_have_value("docs")
    expect(docs).to_be_visible()
    expect(mail).to_have_count(0)
    search.press("Enter")
    expect(page.get_by_test_id("plugins-pane")).to_be_visible()
    expect(search).to_have_value("docs")
    expect(docs).to_be_visible()
    expect(mail).to_have_count(0)
    page.get_by_test_id("plugins-remove").click()
    expect(page.get_by_text("Paste a key to connect apps.")).to_be_visible()
    page.get_by_role("button", name="Close Plugins").click()


def test_plugins_search_filters_without_enter(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    page.get_by_test_id("open-plugins").click()
    _plugins_key_form(page)
    page.get_by_label("Plugins key").fill("ak-test-secret-search")
    page.get_by_test_id("plugins-save").click()
    expect(page.get_by_test_id("plugins-key-saved")).to_contain_text("Key saved")
    mail = page.get_by_test_id("plugin-row-mail")
    docs = page.get_by_test_id("plugin-row-docs")
    expect(mail).to_be_visible()
    expect(docs).to_be_visible()
    search = page.get_by_label("Search apps")
    expect(search).to_have_attribute("placeholder", "Search apps")
    search.fill("docs")
    expect(search).to_have_value("docs")
    expect(docs).to_be_visible()
    expect(mail).to_have_count(0)
    search.fill("")
    expect(search).to_have_value("")
    expect(mail).to_be_visible()
    expect(docs).to_be_visible()
    page.get_by_test_id("plugins-remove").click()
    expect(page.get_by_text("Paste a key to connect apps.")).to_be_visible()
    page.get_by_role("button", name="Close Plugins").click()


def test_plugins_closed_wheel_does_not_open_and_one_close(
    page: Page, client_url: str, host_url: str
) -> None:
    pair_fresh(page, client_url, host_url)
    hatch = page.locator('[data-shell="hatch"]')
    expect(hatch).to_have_attribute("data-hatch-open", "0")
    expect(hatch).to_have_css("pointer-events", "none")
    expect(page.get_by_test_id("plugins-pane")).to_have_count(0)
    thread = page.get_by_test_id("thread-pane")
    expect(thread).to_be_visible()
    thread.hover()
    page.mouse.wheel(0, 800)
    expect(page.get_by_test_id("plugins-pane")).to_have_count(0)
    expect(hatch).to_have_attribute("data-hatch-open", "0")
    page.get_by_test_id("open-plugins").click()
    expect(page.get_by_test_id("plugins-pane")).to_be_visible()
    expect(hatch).to_have_attribute("data-hatch-open", "1")
    expect(hatch).to_have_css("pointer-events", "auto")
    page.get_by_role("button", name="Close Plugins").click()
    expect(page.get_by_test_id("plugins-pane")).to_have_count(0)
    expect(hatch).to_have_attribute("data-hatch-open", "0")
    expect(hatch).to_have_css("pointer-events", "none")
