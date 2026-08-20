from __future__ import annotations

import uuid

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import create_named_bot, pair_fresh, send_message

E2E_CARD_KEY = "City"
E2E_CARD_VALUE = "Belgrade"
E2E_CHILD_ARCHIVED = "Old pal"
E2E_CHILD_NAME = "Spawned pal"
E2E_COMPUTER_TEXT = "Opened Chromium"
E2E_META_TEXT = "Remembered: Prefers short answers without emoji"
E2E_PROGRESS_TEXT = "Checking the desktop"

pytestmark = pytest.mark.live

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_thread_blocks_render(page: Page, client_url: str, host_url: str) -> None:
    name = f"Blocks {uuid.uuid4().hex[:8]}"
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    send_message(page, "please e2e-thread-blocks", name)
    expect(page.get_by_test_id("meta-block")).to_contain_text(E2E_META_TEXT, timeout=15_000)
    expect(page.get_by_test_id("progress-block")).to_contain_text(E2E_PROGRESS_TEXT)
    card = page.get_by_test_id("check-card")
    expect(card).to_contain_text(E2E_CARD_KEY)
    expect(card).to_contain_text(E2E_CARD_VALUE)
    expect(page.get_by_test_id("computer-card")).to_contain_text(E2E_COMPUTER_TEXT)
    expect(page.get_by_test_id("child-bot-card").filter(has_text=E2E_CHILD_NAME)).to_be_enabled()
    expect(page.get_by_test_id("child-bot-card").filter(has_text=E2E_CHILD_ARCHIVED)).to_be_disabled()


def test_thread_reply_attach_banner(page: Page, client_url: str, host_url: str) -> None:
    name = f"Chrome {uuid.uuid4().hex[:8]}"
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    send_message(page, "hello", name)
    bot_msg = page.locator('[data-testid="thread-message"][data-role="bot"]').filter(has_text="ok")
    expect(bot_msg).to_be_visible(timeout=15_000)
    banner = page.get_by_test_id("attention-alert").filter(has_text=name)
    expect(banner).to_be_visible(timeout=8_000)
    expect(banner).to_contain_text("replied")
    send_box = page.get_by_role("button", name="Send", exact=True)
    banner_box = banner.bounding_box()
    send_hit = send_box.bounding_box()
    assert banner_box and send_hit
    assert banner_box["y"] + banner_box["height"] < send_hit["y"]
    page.get_by_test_id("attention-dismiss").click()
    expect(page.get_by_test_id("attention-alert")).to_have_count(0)

    bot_msg.click(button="right", timeout=8_000)
    menu = page.get_by_role("menu", name="Message actions")
    expect(menu).to_be_visible(timeout=8_000)
    menu.get_by_role("menuitem", name="Reply").click(timeout=5_000)
    bar = page.get_by_test_id("reply-bar")
    expect(bar).to_be_visible(timeout=8_000)
    expect(bar).to_contain_text("Replying to")
    expect(bar).to_contain_text("ok")
    send_message(page, "quoted back", name)
    quoted = page.locator('[data-testid="thread-message"][data-role="user"]').filter(
        has_text="quoted back"
    )
    expect(quoted).to_be_visible(timeout=15_000)
    expect(quoted).to_contain_text("ok")

    page.get_by_test_id("attach-files").set_input_files(
        {"name": "shot.png", "mimeType": "image/png", "buffer": TINY_PNG}
    )
    chip = page.get_by_test_id("attach-chip")
    expect(chip).to_contain_text("shot.png", timeout=5_000)
    expect(page.get_by_test_id("attach-preview")).to_be_visible(timeout=5_000)
    chip.get_by_label("Remove shot.png").click(timeout=5_000)
    expect(chip).to_have_count(0)
