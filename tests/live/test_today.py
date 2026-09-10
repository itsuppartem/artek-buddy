from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import bot_row, create_named_bot, pair_fresh, send_message, unique_bot

pytestmark = pytest.mark.live


def test_today_uses_host_attention_not_preview_words(
    page: Page, client_url: str, host_url: str
) -> None:
    trap = unique_bot("Trap")
    speaker = unique_bot("Consent")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, trap)
    send_message(page, "please e2e-no-questions", trap)
    expect(page.locator('[data-testid="thread-message"][data-role="bot"]').last).to_contain_text(
        "No questions remain",
        timeout=20_000,
    )
    create_named_bot(page, speaker)
    send_message(page, "e2e-consent-browse", speaker)
    expect(page.get_by_test_id("consent-card")).to_be_visible(timeout=20_000)
    page.get_by_test_id("workspace-rail").get_by_role("button", name="Today").click()
    today = page.get_by_test_id("today-view")
    expect(today).to_be_visible(timeout=8_000)
    decision = today.locator('[data-task-stage="decision"]')
    expect(decision).to_contain_text(speaker, timeout=15_000)
    expect(decision).not_to_contain_text(trap)


def test_stopped_run_is_not_complete_on_chat_or_today(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("StopToday")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    send_message(page, "please e2e-slow now", name)
    expect(page.get_by_test_id("thread-stop")).to_be_visible(timeout=8_000)
    page.get_by_test_id("thread-stop").click()
    header = page.get_by_test_id("thread-header")
    expect(header).to_contain_text("Stopped", timeout=15_000)
    expect(header).not_to_contain_text("Ready")
    summary = page.get_by_test_id("work-summary")
    expect(summary).to_contain_text("Stopped by you")
    expect(summary).not_to_contain_text("Task is complete")
    page.get_by_test_id("open-work-log").click()
    log = page.get_by_test_id("work-log-pane")
    expect(log).to_contain_text("Stopped by you")
    expect(log).not_to_contain_text("This run finished")
    page.get_by_test_id("workspace-rail").get_by_role("button", name="Today").click()
    today = page.get_by_test_id("today-view")
    expect(today).to_be_visible(timeout=8_000)
    expect(today.locator('[data-task-stage="ready"]')).not_to_contain_text(name)


def test_today_does_not_mark_hidden_thread_read(page: Page, client_url: str, host_url: str) -> None:
    native_requests = []
    dismiss_requests = []
    page.on(
        "request",
        lambda request: (
            native_requests.append(request)
            if request.url.endswith("/local/notify")
            else dismiss_requests.append(request)
            if request.url.endswith("/local/notify-dismiss")
            else None
        ),
    )
    name = unique_bot("HideRead")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    send_message(page, "please e2e-slow", name)
    page.get_by_test_id("workspace-rail").get_by_role("button", name="Today").click()
    today = page.get_by_test_id("today-view")
    expect(today).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("thread-pane")).to_be_hidden()
    # Opening the chat dismisses leftover native notify for that helper. After Today,
    # a new reply must not be withdrawn just because the helper is still selected.
    dismiss_after_hidden = len(dismiss_requests)
    expect(today).to_contain_text("slow done", timeout=15_000)
    expect(page.get_by_test_id("workspace-attention-count")).to_be_visible(timeout=8_000)
    expect(bot_row(page, name).get_by_test_id("unread-dot")).to_have_count(1)
    speaker_id = bot_row(page, name).get_attribute("data-bot-id")
    assert speaker_id
    assert len(native_requests) == 1
    assert native_requests[0].post_data_json["tag"] == f"artek-buddy:{speaker_id}"
    assert not any(
        (req.post_data_json or {}).get("tag") == f"artek-buddy:{speaker_id}"
        for req in dismiss_requests[dismiss_after_hidden:]
    )
