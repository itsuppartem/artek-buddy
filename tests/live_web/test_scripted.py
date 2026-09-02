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
    expect(composer(page)).to_be_enabled()
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_be_visible(timeout=20_000)
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_have_count(1)


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
    expect(thread.get_by_text(E2E_WORKER_PROGRESS_LINE)).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("subagent-card")).to_have_count(0)
    expect(page.get_by_test_id("thread-stop")).to_be_visible()
    expect(composer(page)).to_be_enabled()
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_be_visible(timeout=20_000)
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_have_count(1)
