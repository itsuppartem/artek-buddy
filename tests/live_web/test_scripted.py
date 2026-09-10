from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import composer, unique_bot
from tests.live_web.helpers import create_named_bot_phone, pair_host_page, send_message_phone

pytestmark = pytest.mark.live


def test_host_page_scripted_reply_on_iphone(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("HelloWeb"))
    send_message_phone(page, "hello")
    expect(page.locator('[data-testid="thread-message"][data-role="bot"]').last).to_contain_text(
        "ok",
        timeout=20_000,
    )


def test_host_page_background_worker_keeps_composer(page: Page, host_url: str) -> None:
    from artek_buddy.runtime.scripted import E2E_WORKER_ACK, E2E_WORKER_SUMMARY

    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("BgWeb"))
    send_message_phone(page, "please e2e-background-worker-chat")
    thread = page.get_by_test_id("thread")
    expect(thread.get_by_text(E2E_WORKER_ACK)).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("subagent-card")).to_have_count(0)
    expect(page.get_by_test_id("thread-stop")).to_be_visible()
    expect(page.get_by_test_id("typing-indicator")).to_be_visible()
    expect(composer(page)).to_be_enabled()
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_be_visible(timeout=20_000)
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_have_count(1)


@pytest.mark.timeout(90)
def test_host_page_work_log_keeps_two_worker_runs(page: Page, host_url: str) -> None:
    from artek_buddy.runtime.scripted import E2E_WORKER_ACK, E2E_WORKER_SUMMARY

    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("WorkHistWeb"))
    send_message_phone(page, "please e2e-background-worker-chat")
    thread = page.get_by_test_id("thread")
    expect(thread.get_by_text(E2E_WORKER_ACK)).to_be_visible(timeout=15_000)
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_be_visible(timeout=20_000)
    send_message_phone(page, "please e2e-background-worker-chat")
    expect(thread.get_by_text(E2E_WORKER_ACK)).to_have_count(2, timeout=15_000)
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_have_count(2, timeout=20_000)
    expect(page.get_by_test_id("open-work-log")).to_have_count(1)
    page.get_by_test_id("open-work-log").click()
    expect(page.get_by_test_id("work-log-pane")).to_be_visible()
    expect(page.get_by_test_id("work-log-worker")).to_have_count(2)
    assert page.get_by_test_id("work-log-run").count() >= 2
    expect(page.get_by_test_id("work-log-usage").first).to_contain_text("in", timeout=8_000)
    page.get_by_label("Close work log").click()
    expect(page.get_by_test_id("work-log-pane")).to_have_count(0)
    expect(page.get_by_test_id("open-work-log")).to_have_count(1)
    page.get_by_test_id("open-work-log").click()
    expect(page.get_by_test_id("work-log-pane")).to_be_visible()
    expect(page.get_by_test_id("work-log-worker")).to_have_count(2)


def test_host_page_worker_progress_line(page: Page, host_url: str) -> None:
    from artek_buddy.runtime.scripted import (
        E2E_WORKER_ACK,
        E2E_WORKER_PROGRESS_LINE,
        E2E_WORKER_SUMMARY,
    )

    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("BgProgressWeb"))
    send_message_phone(page, "please e2e-worker-progress")
    thread = page.get_by_test_id("thread")
    expect(thread.get_by_text(E2E_WORKER_ACK)).to_be_visible(timeout=15_000)
    status = page.get_by_test_id("typing-indicator")
    expect(status).to_contain_text(E2E_WORKER_PROGRESS_LINE, timeout=8_000)
    expect(
        page.get_by_test_id("thread-pane").get_by_text(E2E_WORKER_PROGRESS_LINE, exact=True)
    ).to_have_count(1)
    expect(page.get_by_test_id("thread-header")).not_to_contain_text("Still working")
    expect(page.get_by_test_id("thread-header")).to_contain_text("Working")
    expect(page.get_by_test_id("work-summary")).not_to_contain_text("Still working")
    expect(
        page.locator('[data-testid="thread-message"]').filter(has_text=E2E_WORKER_PROGRESS_LINE)
    ).to_have_count(0)
    expect(page.get_by_test_id("subagent-card")).to_have_count(0)
    expect(page.get_by_test_id("thread-stop")).to_be_visible()
    expect(composer(page)).to_be_enabled()
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_be_visible(timeout=20_000)
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_have_count(1)
    expect(status).to_have_count(0)


def test_host_page_worker_essay_stays_out_of_still_working(page: Page, host_url: str) -> None:
    from artek_buddy.runtime.scripted import (
        E2E_WORKER_ACK,
        E2E_WORKER_ESSAY_MARK,
        E2E_WORKER_PROGRESS_LINE,
        E2E_WORKER_SUMMARY,
    )

    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("BgEssayWeb"))
    send_message_phone(page, "please e2e-worker-essay")
    thread = page.get_by_test_id("thread")
    expect(thread.get_by_text(E2E_WORKER_ACK)).to_be_visible(timeout=15_000)
    status = page.get_by_test_id("typing-indicator")
    expect(status).to_be_visible(timeout=8_000)
    expect(status).to_contain_text(E2E_WORKER_PROGRESS_LINE, timeout=8_000)
    expect(status).not_to_contain_text(E2E_WORKER_ESSAY_MARK)
    expect(page.get_by_test_id("subagent-card")).to_have_count(0)
    expect(page.get_by_test_id("thread-stop")).to_be_visible()
    expect(composer(page)).to_be_enabled()
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_be_visible(timeout=20_000)
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_have_count(1)
    expect(status).to_have_count(0)
    expect(
        page.locator('[data-testid="thread-message"]').filter(has_text=E2E_WORKER_ESSAY_MARK)
    ).to_have_count(0)


def test_unknown_timeout_is_not_failed_retry_on_iphone(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("UnkWeb"))
    send_message_phone(page, "please e2e-unknown-timeout")
    unknown = page.get_by_test_id("run-unknown")
    expect(unknown).to_be_visible(timeout=20_000)
    expect(unknown).to_contain_text("do not send the same command again")
    expect(page.get_by_test_id("run-error")).to_have_count(0)
    expect(page.get_by_test_id("typing-indicator")).to_have_count(0)
    expect(page.get_by_test_id("thread-stop")).to_be_visible()
