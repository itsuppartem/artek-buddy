from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import create_named_bot, open_chat, pair_fresh, send_message, unique_bot

pytestmark = pytest.mark.live


def _open_named(page: Page, client_url: str, host_url: str, prefix: str) -> str:
    name = unique_bot(prefix)
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    return name


def test_scripted_reply_appears(page: Page, client_url: str, host_url: str) -> None:
    name = _open_named(page, client_url, host_url, "Hello")
    send_message(page, "hello", name)
    expect(page.locator('[data-testid="thread-message"][data-role="bot"]').last).to_contain_text(
        "ok",
        timeout=20_000,
    )


def test_scripted_fail_shows_run_error(page: Page, client_url: str, host_url: str) -> None:
    name = _open_named(page, client_url, host_url, "Fail")
    send_message(page, "please e2e-fail now", name)
    expect(page.get_by_test_id("run-error")).to_be_visible(timeout=20_000)
    expect(page.get_by_test_id("run-error")).to_contain_text("scripted fail")
    expect(page.get_by_test_id("run-error")).not_to_contain_text("run failed: run-")
    expect(page.get_by_text("run failed: run-", exact=False)).to_have_count(0)


def test_scripted_fail_raw_id_is_human(page: Page, client_url: str, host_url: str) -> None:
    name = _open_named(page, client_url, host_url, "FailRaw")
    send_message(page, "please e2e-fail-raw now", name)
    expect(page.get_by_test_id("run-error")).to_be_visible(timeout=20_000)
    expect(page.get_by_test_id("run-error")).to_contain_text("The turn failed.")
    expect(page.get_by_text("run failed: run-fb7fd73f-32ed-43ed-a22f-a561aab1600a")).to_have_count(
        0
    )
    expect(page.get_by_test_id("run-error")).not_to_contain_text("run failed: run-")


def test_dead_wait_retries_without_run_error(page: Page, client_url: str, host_url: str) -> None:
    name = _open_named(page, client_url, host_url, "WaitDead")
    send_message(page, "hello", name)
    expect(page.locator('[data-testid="thread-message"][data-role="bot"]').last).to_contain_text(
        "ok",
        timeout=20_000,
    )
    send_message(page, "please e2e-dead-wait", name)
    expect(page.locator('[data-testid="thread-message"][data-role="bot"]').last).to_contain_text(
        "ok",
        timeout=20_000,
    )
    expect(page.get_by_test_id("run-error")).to_have_count(0)
    expect(page.get_by_test_id("run-error").filter(has_text="Send again")).to_have_count(0)
    send_message(page, "hello", name)
    expect(page.locator('[data-testid="thread-message"][data-role="bot"]').last).to_contain_text(
        "ok",
        timeout=20_000,
    )


def test_dead_wait_stuck_shows_run_error(page: Page, client_url: str, host_url: str) -> None:
    name = _open_named(page, client_url, host_url, "WaitStuck")
    send_message(page, "hello", name)
    expect(page.locator('[data-testid="thread-message"][data-role="bot"]').last).to_contain_text(
        "ok",
        timeout=20_000,
    )
    send_message(page, "please e2e-dead-wait-stuck", name)
    err = page.get_by_test_id("run-error")
    expect(err).to_be_visible(timeout=20_000)
    expect(err).to_contain_text("The turn failed.")
    expect(err).to_contain_text("Send again")
    send_message(page, "hello", name)
    expect(page.locator('[data-testid="thread-message"][data-role="bot"]').last).to_contain_text(
        "ok",
        timeout=20_000,
    )


def test_scripted_consent_deny(page: Page, client_url: str, host_url: str) -> None:
    name = _open_named(page, client_url, host_url, "Deny")
    send_message(page, "e2e-consent-browse", name)
    card = page.get_by_test_id("consent-card")
    expect(card).to_be_visible(timeout=20_000)
    page.get_by_test_id("ask-option").filter(has_text="Deny").click()
    expect(card).to_have_attribute("data-status", "answered", timeout=20_000)
    expect(card.get_by_text("Answered")).to_be_visible()
    expect(page.get_by_test_id("ask-option")).to_have_count(0)


def test_scripted_consent_allow_once(page: Page, client_url: str, host_url: str) -> None:
    name = _open_named(page, client_url, host_url, "Allow")
    send_message(page, "e2e-consent-browse", name)
    card = page.get_by_test_id("consent-card")
    expect(card).to_be_visible(timeout=20_000)
    page.get_by_test_id("ask-option").filter(has_text="Allow once").click()
    expect(card).to_have_attribute("data-status", "answered", timeout=20_000)


def test_scripted_consent_always_page(page: Page, client_url: str, host_url: str) -> None:
    name = _open_named(page, client_url, host_url, "Always")
    send_message(page, "e2e-consent-page", name)
    card = page.get_by_test_id("consent-card")
    expect(card).to_be_visible(timeout=20_000)
    expect(card.get_by_test_id("ask-detail")).to_contain_text("page_input")
    page.get_by_test_id("ask-option").filter(has_text="Always").click()
    expect(card).to_have_attribute("data-status", "answered", timeout=20_000)


def test_scripted_send_then_distinct_finish_shows_both_and_exits_live(
    page: Page, client_url: str, host_url: str
) -> None:
    from artek_buddy.runtime.scripted import E2E_SEND_ANSWER, E2E_SEND_TEASER

    name = _open_named(page, client_url, host_url, "SendFin")
    send_message(page, "please e2e-send-then-answer", name)
    bots = page.locator('[data-testid="thread-message"][data-role="bot"]')
    expect(bots).to_have_count(2, timeout=20_000)
    expect(bots.nth(0)).to_contain_text(E2E_SEND_TEASER)
    expect(bots.nth(1)).to_contain_text(E2E_SEND_ANSWER)
    expect(page.get_by_test_id("typing-indicator")).to_have_count(0)
    expect(page.get_by_test_id("thread-stop")).to_have_count(0)
    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    open_chat(page, name)
    again = page.locator('[data-testid="thread-message"][data-role="bot"]')
    expect(again).to_have_count(2, timeout=20_000)
    expect(again.nth(0)).to_contain_text(E2E_SEND_TEASER)
    expect(again.nth(1)).to_contain_text(E2E_SEND_ANSWER)
    expect(page.get_by_test_id("typing-indicator")).to_have_count(0)
