from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    arm_page,
    bot_row,
    create_named_bot,
    fulfill_json,
    open_bot_menu,
    pair_fresh,
    unique_bot,
)

pytestmark = pytest.mark.live


def test_proxy_error_retry_reloads_to_pairing(page: Page, client_url: str) -> None:
    arm_page(page)
    page.route("**/local/status", lambda route: route.abort())
    page.goto(client_url)
    card = page.get_by_test_id("proxy-error")
    expect(card).to_be_visible(timeout=20_000)
    page.unroute("**/local/status")
    card.get_by_role("button", name="Retry").click()
    expect(page.get_by_test_id("pairing")).to_be_visible(timeout=20_000)


def test_pairing_form_fields_and_rejected_url(page: Page, client_url: str) -> None:
    arm_page(page)
    page.goto(client_url)
    form = page.get_by_test_id("pairing")
    expect(form).to_be_visible(timeout=20_000)
    expect(form.get_by_test_id("app-mark")).to_be_visible()
    expect(form.locator('img[src="/pairing-mark.png"]')).to_be_visible()
    expect(page.get_by_label("Host URL")).to_be_visible()
    expect(page.get_by_label("Pairing code")).to_be_visible()
    expect(page.get_by_label("Device name")).to_have_value("This computer")
    expect(page.get_by_role("button", name="Pair")).to_be_disabled()
    expect(form.get_by_text("Pair this computer")).to_be_visible()
    expect(form).to_contain_text("On the Pi, create a pairing code. Type it here, then Pair.")
    expect(form).not_to_contain_text("token")
    expect(form).not_to_contain_text("mint")
    expect(page.get_by_test_id("pairing-host-command")).to_contain_text(
        "docker exec artek-buddy python -m artek_buddy pair"
    )

    page.get_by_placeholder("https://host.example").fill("https://evil.example")
    page.get_by_placeholder("XXXX-XXXX").fill("ABCD-EFGH")
    page.get_by_role("button", name="Pair").click()
    expect(page.get_by_test_id("pairing-error")).to_have_text("invalid url")


def test_pairing_rejects_glued_host_url(page: Page, client_url: str) -> None:
    arm_page(page)
    page.goto(client_url)
    form = page.get_by_test_id("pairing")
    expect(form).to_be_visible(timeout=20_000)
    page.get_by_placeholder("https://host.example").fill(
        "http://127.0.0.1:8080http://127.0.0.1:8080"
    )
    page.get_by_placeholder("XXXX-XXXX").fill("ABCD-EFGH")
    page.get_by_role("button", name="Pair").click()
    expect(page.get_by_test_id("pairing-error")).to_have_text("invalid url")


def test_pairing_with_device_name_shows_empty_bots(
    page: Page, client_url: str, host_url: str
) -> None:
    pair_fresh(page, client_url, host_url, device_name="CI laptop")
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    expect(page.get_by_test_id("new-memory")).to_have_count(0)
    expect(page.get_by_test_id("bot-row")).to_have_count(0)
    empty = page.get_by_test_id("empty-bots")
    expect(empty).to_be_visible()
    expect(empty.get_by_text("Create your first bot")).to_be_visible()
    expect(page.get_by_role("button", name="Create bot")).to_be_visible()


def test_create_cancel_and_disabled_until_named(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    page.get_by_role("button", name="New bot").click()
    expect(page.get_by_placeholder("Name this bot")).to_be_visible()
    create = page.get_by_role("button", name="Create", exact=True)
    expect(create).to_be_disabled()
    expect(page.get_by_test_id("computer-mode-hint")).to_contain_text("Team bots share")
    page.get_by_placeholder("Name this bot").fill("soon")
    expect(create).to_be_enabled()
    page.get_by_test_id("create-cancel").click()
    expect(page.get_by_placeholder("Name this bot")).to_have_count(0)
    expect(page.get_by_test_id("bot-row").filter(has_text="soon")).to_have_count(0)


def test_archive_only_bot_shows_empty_inbox(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("Solo")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    open_bot_menu(page, name)
    page.get_by_role("menuitem", name="Archive").click()
    expect(page.get_by_test_id("bot-row")).to_have_count(0)
    inbox = page.get_by_test_id("empty-inbox")
    expect(inbox).to_be_visible(timeout=8_000)
    expect(inbox.get_by_text("Chats are archived")).to_be_visible()
    expect(page.get_by_test_id("archived-count")).to_have_text("1")
    inbox.get_by_role("button", name="Open archived").click()
    expect(page.get_by_test_id("archived-list")).to_be_visible()
    expect(page.locator('[data-testid="archived-bot-row"]').filter(has_text=name)).to_have_count(1)
    page.get_by_test_id("back-inbox").click()
    expect(inbox).to_be_visible()


def test_create_does_not_run_on_name_focus(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("Focus")
    pair_fresh(page, client_url, host_url)
    page.get_by_role("button", name="New bot").click()
    box = page.get_by_placeholder("Name this bot")
    expect(box).to_be_visible()
    box.click()
    box.fill(name)
    expect(page.get_by_role("button", name="Create", exact=True)).to_be_enabled()
    expect(bot_row(page, name)).to_have_count(0)
    page.get_by_role("button", name="Create", exact=True).click()
    expect(bot_row(page, name)).to_have_count(1, timeout=20_000)


def test_auth_error_repair_returns_to_pairing(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    fulfill_json(page, "**/v1/**", 401, '{"detail":"invalid token"}')
    page.reload()
    card = page.get_by_test_id("auth-error")
    expect(card).to_be_visible(timeout=20_000)
    card.get_by_role("button", name="Pair this computer again").click()
    expect(page.get_by_test_id("pairing")).to_be_visible(timeout=20_000)


def test_workspace_events_auth_error_shows_repair(
    page: Page, client_url: str, host_url: str
) -> None:
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    fulfill_json(page, "**/v1/events", 401, '{"detail":"invalid token"}')
    page.reload()
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    card = page.get_by_test_id("auth-error")
    expect(card).to_be_visible(timeout=20_000)
    expect(page.get_by_test_id("pairing")).to_have_count(0)
    card.get_by_role("button", name="Pair this computer again").click()
    expect(page.get_by_test_id("pairing")).to_be_visible(timeout=20_000)


def test_host_error_retry_clears_banner(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    fulfill_json(page, "**/v1/**", 502, '{"detail":"upstream down"}')
    page.reload()
    card = page.get_by_test_id("reconnect-banner")
    expect(card).to_be_visible(timeout=20_000)
    page.unroute("**/v1/**")
    if card.is_visible():
        card.get_by_role("button", name="Retry connection").click()
    expect(card).to_be_hidden(timeout=20_000)
    expect(page.get_by_test_id("thread-pane")).to_be_visible()


def test_action_error_dismiss_clears_banner(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    fulfill_json(page, "**/v1/**", 400, '{"detail":"bad request"}')
    page.reload()
    card = page.get_by_test_id("action-error")
    expect(card).to_be_visible(timeout=20_000)
    card.get_by_role("button", name="Dismiss").click()
    expect(card).to_be_hidden()
