from __future__ import annotations

import uuid

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import bot_row, create_named_bot, dismiss_attention, pair_fresh, send_message

E2E_CARD_KEY = "City"
E2E_CARD_VALUE = "Belgrade"
E2E_CHILD_ARCHIVED = "Old pal"
E2E_CHILD_NAME = "Spawned pal"
E2E_COMPUTER_TEXT = "Opened Chromium"
E2E_META_TEXT = "Remembered: Prefers short answers without emoji"
E2E_PROGRESS_TEXT = "Checking the desktop"
E2E_SLOW_ANSWER = "slow done"

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
    send_message(page, "please e2e-thread-blocks")
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
    other = f"Other {uuid.uuid4().hex[:8]}"
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    create_named_bot(page, other)
    bot_row(page, name).click()
    send_message(page, "please e2e-slow now")
    bot_row(page, other).click()
    # Banner auto-hides in 4s. Catch it while viewing the other bot.
    expect(page.get_by_test_id("attention-alert")).to_contain_text(f"{name} replied", timeout=12_000)
    dismiss_attention(page)
    bot_msg = page.locator('[data-testid="thread-message"][data-role="bot"]').filter(
        has_text=E2E_SLOW_ANSWER
    ).last
    expect(bot_msg).to_be_visible(timeout=8_000)

    bot_msg.click(button="right", force=True, timeout=5_000)
    page.get_by_role("menu", name="Message actions").get_by_role("menuitem", name="Reply").click(
        timeout=5_000
    )
    expect(page.get_by_text(f"Replying to {name}")).to_be_visible(timeout=5_000)
    send_message(page, "quoted back")
    user = page.locator('[data-testid="thread-message"][data-role="user"]').last
    expect(user).to_contain_text("quoted back", timeout=8_000)
    expect(user).to_contain_text(E2E_SLOW_ANSWER)

    page.get_by_test_id("attach-files").set_input_files(
        {"name": "shot.png", "mimeType": "image/png", "buffer": TINY_PNG}
    )
    chip = page.get_by_test_id("attach-chip")
    expect(chip).to_contain_text("shot.png", timeout=5_000)
    expect(page.get_by_test_id("attach-preview")).to_be_visible(timeout=5_000)
    chip.get_by_label("Remove shot.png").click(timeout=5_000)
    expect(chip).to_have_count(0)
