from __future__ import annotations

import re
import uuid

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import composer, create_named_bot, open_settings, pair_fresh, send_message

# Keep in lockstep with artek_buddy.runtime.scripted (avoid importing the runtime here).
E2E_ASK_QUESTION = "Which city?"
E2E_CARD_KEY = "City"
E2E_CARD_VALUE = "Belgrade"
E2E_CHILD_ARCHIVED = "Old pal"
E2E_CHILD_NAME = "Spawned pal"
E2E_COMPUTER_TEXT = "Opened Chromium"
E2E_DRAFT_ANSWER = "Belgrade is 22°C and clear."
E2E_DRAFT_LEAK = "grade's current weather from a public API"
E2E_META_TEXT = "Remembered: Prefers short answers without emoji"
E2E_PROGRESS_TEXT = "Checking the desktop"
E2E_SUBAGENT_NAME = "Researcher"

pytestmark = pytest.mark.live

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _dismiss_banner(page: Page) -> None:
    banner = page.get_by_test_id("attention-alert")
    if banner.count():
        banner.click(timeout=2_000)


def test_thread_blocks_and_consent(page: Page, client_url: str, host_url: str) -> None:
    name = f"Blocks {uuid.uuid4().hex[:8]}"
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)

    send_message(page, "please e2e-markdown-preview")
    expect(page.locator('[data-testid=thread-message][data-role=bot]').last.locator("strong")).to_have_text(
        "Belgrade",
        timeout=15_000,
    )

    send_message(page, "please e2e-hide-draft")
    expect(page.get_by_text(E2E_DRAFT_ANSWER)).to_be_visible(timeout=15_000)
    expect(page.get_by_text(E2E_DRAFT_LEAK)).to_have_count(0)

    send_message(page, "please e2e-thread-blocks")
    expect(page.get_by_test_id("meta-block")).to_contain_text(E2E_META_TEXT, timeout=15_000)
    expect(page.get_by_test_id("progress-block")).to_contain_text(E2E_PROGRESS_TEXT)
    card = page.get_by_test_id("check-card")
    expect(card).to_contain_text(E2E_CARD_KEY)
    expect(card).to_contain_text(E2E_CARD_VALUE)
    expect(page.get_by_test_id("computer-card")).to_contain_text(E2E_COMPUTER_TEXT)
    live = page.get_by_test_id("child-bot-card").filter(has_text=E2E_CHILD_NAME)
    gone = page.get_by_test_id("child-bot-card").filter(has_text=E2E_CHILD_ARCHIVED)
    expect(live).to_be_enabled()
    expect(gone).to_be_disabled()

    send_message(page, "please e2e-send-file")
    file_card = page.get_by_test_id("file-card")
    expect(file_card).to_contain_text("notes.txt", timeout=15_000)
    file_card.get_by_role("button", name="Download").click()
    expect(page.get_by_test_id("file-saved")).to_contain_text("Downloads", timeout=10_000)

    send_message(page, "please e2e-ask")
    ask = page.get_by_test_id("ask-card")
    expect(ask).to_contain_text(E2E_ASK_QUESTION, timeout=15_000)
    expect(page.get_by_test_id("ask-option").filter(has_text="Belgrade")).to_be_visible()
    ask.get_by_text("Type custom reply…").click()
    page.get_by_label("Answer").fill("Lisbon")
    page.get_by_role("button", name="Send answer").click()
    expect(ask).to_have_attribute("data-status", "answered", timeout=15_000)

    send_message(page, "e2e-consent-browse")
    consent = page.get_by_test_id("consent-card")
    expect(consent).to_be_visible(timeout=15_000)
    page.get_by_test_id("ask-option").filter(has_text="Allow once").click()
    expect(consent).to_have_attribute("data-status", "answered", timeout=15_000)

    send_message(page, "e2e-consent-page")
    page_card = page.get_by_test_id("consent-card").last
    expect(page_card).to_be_visible(timeout=15_000)
    page.get_by_test_id("ask-option").filter(has_text="Always").click()
    expect(page_card).to_have_attribute("data-status", "answered", timeout=15_000)


def test_thread_chrome_attach_stop_banner(page: Page, client_url: str, host_url: str) -> None:
    name = f"Chrome {uuid.uuid4().hex[:8]}"
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)

    send_message(page, "hello")
    expect(page.locator('[data-testid=thread-message][data-role=bot]').last).to_contain_text(
        "ok",
        timeout=15_000,
    )
    banner = page.get_by_test_id("attention-alert")
    expect(banner).to_contain_text(f"{name} replied", timeout=6_000)
    _dismiss_banner(page)

    page.locator('[data-testid=thread-message][data-role=bot]').last.click(button="right")
    page.get_by_role("menuitem", name="Reply").click()
    expect(page.get_by_text(f"Replying to {name}")).to_be_visible()
    send_message(page, "quoted back")
    user = page.locator('[data-testid=thread-message][data-role=user]').last
    expect(user).to_contain_text("quoted back")
    expect(user).to_contain_text("ok")

    box = composer(page)
    box.fill("line one")
    box.press("Shift+Enter")
    box.type("line two")
    expect(box).to_have_value("line one\nline two")
    box.press("Enter")
    expect(page.locator('[data-testid=thread-message][data-role=user]').last).to_contain_text("line one")

    page.get_by_test_id("attach-files").set_input_files(
        {"name": "shot.png", "mimeType": "image/png", "buffer": TINY_PNG}
    )
    chip = page.get_by_test_id("attach-chip")
    expect(chip).to_contain_text("shot.png")
    expect(page.get_by_test_id("attach-preview")).to_be_visible()
    chip.get_by_label("Remove shot.png").click()
    expect(chip).to_have_count(0)

    send_message(page, "please e2e-slow now")
    expect(page.get_by_test_id("typing-indicator")).to_be_visible(timeout=5_000)
    page.get_by_role("button", name="Stop").click(timeout=5_000)
    expect(page.get_by_test_id("run-error")).to_contain_text("Stopped.", timeout=10_000)

    send_message(page, "please e2e-fail now")
    expect(page.get_by_test_id("run-error")).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("attention-alert")).to_contain_text(f"{name} failed", timeout=6_000)
    _dismiss_banner(page)

    open_settings(page, name)
    notify = page.get_by_test_id("notify-on-finish")
    if notify.is_checked():
        with page.expect_response(
            lambda r: r.request.method == "PATCH" and "/v1/bots/" in r.url,
            timeout=10_000,
        ):
            notify.uncheck()
    expect(notify).not_to_be_checked()

    send_message(page, "please e2e-takeover")
    expect(page.get_by_test_id("attention-alert")).to_contain_text(f"{name} needs you", timeout=6_000)
    _dismiss_banner(page)

    send_message(page, "please e2e-ask")
    expect(page.get_by_test_id("ask-card")).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("attention-alert")).to_contain_text(f"{name} is asking", timeout=6_000)


def test_thread_subagent_stop_and_restart(page: Page, client_url: str, host_url: str) -> None:
    name = f"Workers {uuid.uuid4().hex[:8]}"
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    send_message(page, "please e2e-subagent")
    card = page.get_by_test_id("subagent-card")
    expect(card).to_contain_text(f"#1 {E2E_SUBAGENT_NAME}", timeout=15_000)
    stop = card.get_by_role("button", name="Stop")
    if stop.count():
        stop.click(timeout=5_000)
        expect(card).to_have_attribute("data-status", "cancelled", timeout=10_000)
    expect(card.get_by_role("button", name="Restart")).to_be_visible(timeout=10_000)
    card.get_by_role("button", name="Restart").click()
    expect(card).to_have_attribute("data-status", re.compile(r"queued|running"), timeout=10_000)
