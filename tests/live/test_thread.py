from __future__ import annotations

import base64

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    bot_row,
    composer,
    create_named_bot,
    cut_host,
    ensure_model,
    open_chat,
    pair_fresh,
    restore_host,
    send_message,
    thread_header,
    unique_bot,
)

E2E_CARD_KEY = "City"
E2E_CARD_VALUE = "Belgrade"
E2E_CHILD_ARCHIVED = "Old pal"
E2E_CHILD_NAME = "Spawned pal"
E2E_COMPUTER_TEXT = "Opened Chromium"
E2E_META_TEXT = "Remembered: Prefers short answers without emoji"
E2E_PROGRESS_TEXT = "Checking the desktop"
E2E_ASK_QUESTION = "Which city?"
E2E_ASK_DETAIL = "I can open Wikipedia on the desktop after you pick one."
E2E_ASK_FREE_QUESTION = "What should I call you?"
E2E_DRAFT_LEAK = "grade's current weather from a public API"
E2E_OLDER_PREFIX = "e2e-old-"

pytestmark = pytest.mark.live

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _named(page: Page, client_url: str, host_url: str, prefix: str) -> str:
    name = unique_bot(prefix)
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    return name


def test_thread_blocks_render_and_child_opens_other_chat(
    page: Page, client_url: str, host_url: str
) -> None:
    name = _named(page, client_url, host_url, "Blocks")
    send_message(page, "please e2e-thread-blocks", name)
    expect(page.get_by_test_id("meta-block")).to_contain_text(E2E_META_TEXT, timeout=15_000)
    expect(page.get_by_test_id("progress-block")).to_contain_text(E2E_PROGRESS_TEXT)
    card = page.get_by_test_id("check-card")
    expect(card).to_contain_text(E2E_CARD_KEY)
    expect(card).to_contain_text(E2E_CARD_VALUE)
    expect(page.get_by_test_id("computer-card")).to_contain_text(E2E_COMPUTER_TEXT)
    child = page.get_by_test_id("child-bot-card").filter(has_text=E2E_CHILD_NAME)
    expect(child).to_be_enabled()
    expect(
        page.get_by_test_id("child-bot-card").filter(has_text=E2E_CHILD_ARCHIVED)
    ).to_be_disabled()
    child.click()
    expect(thread_header(page)).to_contain_text(E2E_CHILD_NAME, timeout=8_000)
    expect(thread_header(page)).not_to_contain_text(name)


def test_ask_other_bot_card_opens_them_then_asker_answers(
    page: Page, client_url: str, host_url: str
) -> None:
    asker = unique_bot("AskWin")
    knows = unique_bot("KnowsWin")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, knows)
    create_named_bot(page, asker)
    send_message(page, f"please e2e-ask-bot {knows} | what city do you know", asker)
    card = page.get_by_test_id("child-bot-card").filter(has_text=knows).first
    expect(card).to_be_enabled(timeout=15_000)
    expect(page.get_by_text(f"Asked {knows}", exact=False)).to_be_visible()
    card.click()
    expect(thread_header(page)).to_contain_text(knows, timeout=8_000)
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(
            has_text="what city do you know"
        )
    ).to_be_visible(timeout=15_000)
    expect(
        page.locator('[data-testid="thread-message"][data-role="bot"]').filter(
            has_text="ready to answer"
        )
    ).to_be_visible(timeout=15_000)
    open_chat(page, asker)
    expect(
        page.locator('[data-testid="thread-message"][data-role="bot"]').filter(has_text="Subotica")
    ).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("computer-card")).to_have_count(0)


def test_open_chat_has_no_replied_banner(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Here")
    send_message(page, "hello", name)
    expect(
        page.locator('[data-testid="thread-message"][data-role="bot"]').filter(has_text="ok")
    ).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("attention-alert")).to_have_count(0)


def test_other_chat_replied_banner_opens_that_bot(
    page: Page, client_url: str, host_url: str
) -> None:
    speaker = unique_bot("Talk")
    watcher = unique_bot("Watch")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, speaker)
    create_named_bot(page, watcher)
    expect(page.get_by_test_id("attention-alert")).to_have_count(0)
    open_chat(page, speaker)
    box = composer(page)
    box.fill("please e2e-slow")
    expect(box).to_have_value("please e2e-slow")
    box.press("Enter")
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(
            has_text="please e2e-slow"
        )
    ).to_be_visible()
    open_chat(page, watcher)
    expect(thread_header(page)).to_contain_text(watcher)
    banner = page.get_by_test_id("attention-alert")
    expect(banner).to_contain_text(f"{speaker} replied", timeout=15_000)
    expect(thread_header(page)).to_contain_text(watcher)
    send_box = page.get_by_role("button", name="Send", exact=True)
    banner_box = banner.bounding_box()
    send_hit = send_box.bounding_box()
    assert banner_box and send_hit
    assert banner_box["y"] + banner_box["height"] < send_hit["y"]
    banner.get_by_role("button").first.click()
    expect(thread_header(page)).to_contain_text(speaker, timeout=8_000)


def test_thread_reply_quote_and_cancel(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Quote")
    send_message(page, "hello", name)
    bot_msg = page.locator('[data-testid="thread-message"][data-role="bot"]').filter(has_text="ok")
    expect(bot_msg).to_be_visible(timeout=15_000)
    bot_msg.click(button="right", timeout=8_000)
    menu = page.get_by_role("menu", name="Message actions")
    expect(menu).to_be_visible(timeout=8_000)
    menu.get_by_role("menuitem", name="Reply").click(timeout=5_000)
    bar = page.get_by_test_id("reply-bar")
    expect(bar).to_be_visible(timeout=8_000)
    expect(bar).to_contain_text("Replying to")
    page.get_by_label("Cancel reply").click()
    expect(bar).to_have_count(0)
    bot_msg.click(button="right", timeout=8_000)
    page.get_by_role("menuitem", name="Reply").click(timeout=5_000)
    expect(bar).to_be_visible()
    send_message(page, "quoted back", name)
    quoted = page.locator('[data-testid="thread-message"][data-role="user"]').filter(
        has_text="quoted back"
    )
    expect(quoted).to_be_visible(timeout=15_000)
    expect(quoted).to_contain_text("ok")


def test_markdown_link_opens_and_has_link_actions(
    page: Page, client_url: str, host_url: str
) -> None:
    name = _named(page, client_url, host_url, "Links")
    page.context.grant_permissions(
        ["clipboard-read", "clipboard-write"],
        origin=client_url.rstrip("/"),
    )
    page.context.route(
        "https://example.com/**",
        lambda route: route.fulfill(status=200, content_type="text/html", body="docs"),
    )
    send_message(page, "please e2e-markdown-preview", name)
    link = page.get_by_role("link", name="Open docs", exact=True)
    expect(link).to_have_attribute("href", "https://example.com/artek-buddy", timeout=15_000)

    with page.expect_popup() as opened:
        link.click()
    expect(opened.value).to_have_url("https://example.com/artek-buddy")
    opened.value.close()

    link.click(button="right")
    menu = page.get_by_role("menu", name="Message actions")
    expect(menu.get_by_role("menuitem", name="Open in browser", exact=True)).to_be_visible()
    copy_url = menu.get_by_role("menuitem", name="Copy URL", exact=True)
    expect(copy_url).to_be_visible()
    expect(menu.get_by_role("menuitem", name="Reply", exact=True)).to_be_visible()
    copy_url.click()
    expect(menu.get_by_role("menuitem", name="URL copied", exact=True)).to_be_visible()
    assert page.evaluate("navigator.clipboard.readText()") == "https://example.com/artek-buddy"


def test_composer_paste_screenshot_attaches_chip(
    page: Page, client_url: str, host_url: str
) -> None:
    _named(page, client_url, host_url, "Paste")
    box = composer(page)
    box.click()
    png_b64 = base64.b64encode(TINY_PNG).decode("ascii")
    box.evaluate(
        """(el, b64) => {
          const bytes = Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0));
          const file = new File([bytes], "", { type: "image/png" });
          const data = new DataTransfer();
          data.items.add(file);
          const event = new Event("paste", { bubbles: true, cancelable: true });
          Object.defineProperty(event, "clipboardData", { value: data });
          el.dispatchEvent(event);
        }""",
        png_b64,
    )
    chip = page.get_by_test_id("attach-chip")
    expect(chip).to_contain_text("screenshot-1.png", timeout=5_000)
    expect(page.get_by_test_id("attach-preview")).to_be_visible(timeout=5_000)
    expect(box).to_have_value("")


def test_composer_paste_text_does_not_attach(page: Page, client_url: str, host_url: str) -> None:
    _named(page, client_url, host_url, "TextPaste")
    box = composer(page)
    box.click()
    page.context.grant_permissions(
        ["clipboard-read", "clipboard-write"],
        origin=client_url.rstrip("/"),
    )
    page.evaluate("navigator.clipboard.writeText('hello from the clipboard')")
    box.press("Control+V")
    expect(box).to_have_value("hello from the clipboard")
    expect(page.get_by_test_id("attach-chip")).to_have_count(0)


def test_composer_drop_attaches_chip(page: Page, client_url: str, host_url: str) -> None:
    _named(page, client_url, host_url, "Drop")
    page.get_by_test_id("thread-composer").evaluate(
        """el => {
          const data = new DataTransfer();
          data.items.add(new File([new Uint8Array([65, 66, 67])], "drop.txt", {type: "text/plain"}));
          el.dispatchEvent(new DragEvent("drop", {bubbles: true, cancelable: true, dataTransfer: data}));
        }"""
    )
    expect(page.get_by_test_id("attach-chip")).to_contain_text("drop.txt", timeout=5_000)


def test_attach_via_plus(page: Page, client_url: str, host_url: str) -> None:
    _named(page, client_url, host_url, "Plus")
    with page.expect_file_chooser() as chooser:
        page.get_by_role("button", name="Attach files").click()
    chooser.value.set_files({"name": "shot.png", "mimeType": "image/png", "buffer": TINY_PNG})
    chip = page.get_by_test_id("attach-chip")
    expect(chip).to_contain_text("shot.png", timeout=5_000)
    expect(page.get_by_test_id("attach-preview")).to_be_visible(timeout=5_000)
    chip.get_by_label("Remove shot.png").click(timeout=5_000)
    expect(chip).to_have_count(0)


def test_composer_shift_enter_and_undo(page: Page, client_url: str, host_url: str) -> None:
    _named(page, client_url, host_url, "Keys")
    box = composer(page)
    box.fill("line one")
    box.press("Shift+Enter")
    box.type("line two")
    expect(box).to_have_value("line one\nline two")
    box.press("Control+z")
    expect(box).not_to_have_value("line one\nline two")
    expect(page.locator('[data-testid="thread-message"][data-role="user"]')).to_have_count(0)


def test_composer_ctrl_a_does_not_send(page: Page, client_url: str, host_url: str) -> None:
    _named(page, client_url, host_url, "Select")
    box = composer(page)
    draft = "keep this draft"
    box.fill(draft)
    expect(box).to_have_value(draft)
    box.press("Control+a")
    expect(box).to_have_value(draft)
    selected = box.evaluate("el => el.selectionEnd - el.selectionStart")
    assert selected == len(draft)
    expect(page.locator('[data-testid="thread-message"][data-role="user"]')).to_have_count(0)
    box.press("Enter")
    bubble = page.locator('[data-testid="thread-message"][data-role="user"]').get_by_test_id(
        "user-text"
    )
    expect(bubble).to_be_visible(timeout=8_000)
    expect(bubble).to_have_js_property("textContent", draft)
    expect(page.locator('[data-testid="thread-message"][data-role="user"]')).to_have_count(1)


def test_composer_placeholder_does_not_clip_mid_word(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("ResearchOverflowName")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    box = composer(page)
    placeholder = box.get_attribute("placeholder") or ""
    full = f"Message {name}"
    assert placeholder.startswith("Message ")
    assert placeholder != "Message Resea"
    if placeholder != full:
        assert placeholder.endswith("…")
        assert not full.startswith(placeholder)
    else:
        raise AssertionError(f"long name stayed untruncated: {placeholder}")


def test_user_bubble_keeps_shift_enter_newline(page: Page, client_url: str, host_url: str) -> None:
    _named(page, client_url, host_url, "Break")
    box = composer(page)
    box.fill("line one")
    box.press("Shift+Enter")
    box.type("line two")
    expect(box).to_have_value("line one\nline two")
    box.press("Enter")
    bubble = page.locator('[data-testid="thread-message"][data-role="user"]').get_by_test_id(
        "user-text"
    )
    expect(bubble).to_be_visible(timeout=8_000)
    expect(bubble).to_have_css("white-space", "pre-wrap")
    expect(bubble).to_have_js_property("textContent", "line one\nline two")


def test_load_earlier_messages(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Older")
    other = unique_bot("Other")
    send_message(page, "please e2e-load-earlier", name)
    create_named_bot(page, other)
    open_chat(page, name)
    earlier = page.get_by_test_id("load-earlier")
    expect(earlier).to_be_visible(timeout=15_000)
    earlier.click()
    expect(page.get_by_text(f"{E2E_OLDER_PREFIX}00", exact=True)).to_be_visible(timeout=15_000)


def test_download_and_load_earlier_look_like_controls(
    page: Page, client_url: str, host_url: str
) -> None:
    name = _named(page, client_url, host_url, "Chrome")
    with page.expect_file_chooser() as chooser:
        page.get_by_role("button", name="Attach files").click()
    chooser.value.set_files({"name": "shot.png", "mimeType": "image/png", "buffer": TINY_PNG})
    expect(page.get_by_test_id("attach-chip")).to_contain_text("shot.png", timeout=5_000)
    send_message(page, "my shot", name)
    user_card = (
        page.locator('[data-testid="thread-message"][data-role="user"]')
        .filter(has_text="my shot")
        .get_by_test_id("file-card")
    )
    download = user_card.get_by_test_id("file-download")
    expect(download).to_be_visible(timeout=8_000)
    expect(download).to_have_accessible_name("Download shot.png")
    other = unique_bot("Other")
    send_message(page, "please e2e-load-earlier", name)
    create_named_bot(page, other)
    open_chat(page, name)
    earlier = page.get_by_test_id("load-earlier")
    expect(earlier).to_be_visible(timeout=15_000)
    expect(earlier).to_have_accessible_name("Load earlier messages")
    earlier.click()
    expect(page.get_by_text(f"{E2E_OLDER_PREFIX}00", exact=True)).to_be_visible(timeout=15_000)
    leftover = page.get_by_test_id("load-earlier")
    if leftover.count() and leftover.first.is_visible():
        leftover.click()
        expect(page.get_by_text(f"{E2E_OLDER_PREFIX}00", exact=True)).to_be_visible()
    expect(page.get_by_test_id("thread-start")).to_contain_text("Beginning of this chat.")


def test_ask_options_custom_and_detail(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Ask")
    send_message(page, "please e2e-ask", name)
    card = page.get_by_test_id("ask-card")
    expect(card).to_be_visible(timeout=15_000)
    expect(card).to_contain_text(E2E_ASK_QUESTION)
    expect(page.get_by_test_id("ask-detail")).to_contain_text(E2E_ASK_DETAIL)
    page.get_by_text("Type custom reply…").click()
    page.get_by_label("Answer").fill("Lisbon")
    page.get_by_role("button", name="Send answer").click()
    expect(card).to_contain_text("Answered: Lisbon", timeout=8_000)
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(has_text="Lisbon")
    ).to_have_count(0)
    expect(
        page.get_by_test_id("thread").get_by_text("I continued after your help.", exact=True)
    ).to_be_visible(timeout=8_000)


def test_ask_free_edit_first(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Free")
    send_message(page, "please e2e-ask-free", name)
    card = page.get_by_test_id("ask-card")
    expect(card).to_be_visible(timeout=15_000)
    expect(card).to_contain_text(E2E_ASK_FREE_QUESTION)
    page.get_by_role("button", name="Edit first").click()
    page.get_by_label("Answer").fill("Sam")
    page.get_by_role("button", name="Send answer").click()
    expect(card).to_contain_text("Answered: Sam", timeout=8_000)
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(has_text="Sam")
    ).to_have_count(0)
    expect(
        page.get_by_test_id("thread").get_by_text("I continued after your help.", exact=True)
    ).to_be_visible(timeout=8_000)


def test_ask_free_send_it(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "SendIt")
    send_message(page, "please e2e-ask-free", name)
    card = page.get_by_test_id("ask-card")
    page.get_by_role("button", name="Send it").click()
    expect(card).to_contain_text("Answered: approved", timeout=8_000)
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(has_text="approved")
    ).to_have_count(0)
    expect(
        page.get_by_test_id("thread").get_by_text("I continued after your help.", exact=True)
    ).to_be_visible(timeout=8_000)


def test_hidden_live_draft_is_not_shown(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Draft")
    send_message(page, "please e2e-hide-draft", name)
    expect(page.get_by_text(E2E_DRAFT_LEAK)).to_have_count(0)
    expect(page.locator('[data-testid="thread-message"][data-role="bot"]').last).to_contain_text(
        "Belgrade is 22°C",
        timeout=15_000,
    )


def test_file_download_and_image_preview(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "File")
    send_message(page, "please e2e-send-file", name)
    card = page.get_by_test_id("file-card")
    expect(card).to_contain_text("notes.txt", timeout=15_000)
    card.get_by_role("button", name="Download").click()
    expect(page.get_by_test_id("file-saved")).to_contain_text("Saved to", timeout=8_000)
    send_message(page, "please e2e-send-image", name)
    image = page.get_by_test_id("file-card").filter(has_text="shot.png")
    expect(image).to_be_visible(timeout=15_000)
    expect(image.get_by_test_id("file-preview")).to_be_visible()


def test_attachment_chip_does_not_return_on_later_send(
    page: Page, client_url: str, host_url: str
) -> None:
    name = _named(page, client_url, host_url, "Chip")
    with page.expect_file_chooser() as chooser:
        page.get_by_role("button", name="Attach files").click()
    chooser.value.set_files({"name": "once.txt", "mimeType": "text/plain", "buffer": b"once"})
    expect(page.get_by_test_id("attach-chip")).to_contain_text("once.txt", timeout=5_000)
    send_message(page, "with file", name)
    expect(page.get_by_test_id("attach-chip")).to_have_count(0)
    first = page.locator('[data-testid="thread-message"][data-role="user"]').filter(
        has_text="with file"
    )
    expect(first.get_by_test_id("file-card")).to_be_visible(timeout=8_000)
    send_message(page, "plain later", name)
    later = page.locator('[data-testid="thread-message"][data-role="user"]').filter(
        has_text="plain later"
    )
    expect(later).to_be_visible(timeout=8_000)
    expect(later.get_by_test_id("file-card")).to_have_count(0)
    expect(page.get_by_test_id("attach-chip")).to_have_count(0)


def test_typing_indicator_and_lead_stop(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Stop")
    box = composer(page)
    box.fill("please e2e-slow")
    expect(box).to_have_value("please e2e-slow")
    box.press("Enter")
    expect(page.get_by_test_id("typing-indicator")).to_be_visible(timeout=8_000)
    page.get_by_test_id("thread-stop").click()
    expect(page.get_by_test_id("run-error")).to_be_visible(timeout=15_000)


def test_stop_does_not_append_completed_essay(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Essay")
    box = composer(page)
    box.fill("please e2e-slow")
    expect(box).to_have_value("please e2e-slow")
    box.press("Enter")
    expect(page.get_by_test_id("thread-stop")).to_be_visible(timeout=8_000)
    page.get_by_test_id("thread-stop").click()
    expect(page.get_by_test_id("run-error")).to_be_visible(timeout=15_000)
    page.wait_for_timeout(3_000)
    expect(page.get_by_test_id("thread").get_by_text("slow done")).to_have_count(0)
    expect(bot_row(page, name)).not_to_contain_text("slow done")


def test_stop_late_complete_shows_stopped_and_drops_model_text(
    page: Page, client_url: str, host_url: str
) -> None:
    name = _named(page, client_url, host_url, "LateStop")
    box = composer(page)
    box.fill("please e2e-late-complete")
    expect(box).to_have_value("please e2e-late-complete")
    box.press("Enter")
    expect(page.get_by_test_id("thread-stop")).to_be_visible(timeout=8_000)
    page.get_by_test_id("thread-stop").click()
    expect(page.get_by_test_id("run-error")).to_contain_text("Stopped.", timeout=15_000)
    page.wait_for_timeout(3_000)
    expect(page.get_by_test_id("thread").get_by_text("pong")).to_have_count(0)
    expect(bot_row(page, name)).not_to_contain_text("pong")


def test_streaming_turn_keeps_last_card_in_view(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Pin")
    send_message(page, "please e2e-load-earlier", name)
    last = (
        page.get_by_test_id("thread")
        .locator('[data-testid="thread-message"][data-role="bot"]')
        .filter(has_text=f"{E2E_OLDER_PREFIX}50")
    )
    expect(last).to_be_visible(timeout=15_000)
    expect(last).to_be_in_viewport()


def test_switch_back_lands_on_latest_messages(page: Page, client_url: str, host_url: str) -> None:
    first = unique_bot("HistA")
    second = unique_bot("HistB")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, first)
    send_message(page, "please e2e-load-earlier", first)
    create_named_bot(page, second)
    open_chat(page, first)
    last = (
        page.get_by_test_id("thread")
        .locator('[data-testid="thread-message"][data-role="bot"]')
        .filter(has_text=f"{E2E_OLDER_PREFIX}50")
    )
    expect(last).to_be_visible(timeout=15_000)
    expect(last).to_be_in_viewport()


def test_dismissed_attention_stays_gone_after_switch(
    page: Page, client_url: str, host_url: str
) -> None:
    speaker = unique_bot("AskA")
    watcher = unique_bot("AskB")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, speaker)
    create_named_bot(page, watcher)
    open_chat(page, speaker)
    box = composer(page)
    box.fill("please e2e-takeover")
    expect(box).to_have_value("please e2e-takeover")
    box.press("Enter")
    open_chat(page, watcher)
    banner = page.get_by_test_id("attention-alert")
    expect(banner).to_contain_text(f"{speaker} needs you", timeout=15_000)
    page.get_by_test_id("attention-dismiss").click()
    expect(banner).to_have_count(0)
    open_chat(page, speaker)
    open_chat(page, watcher)
    expect(page.get_by_test_id("attention-alert").filter(has_text="needs you")).to_have_count(0)


def test_answered_consent_pill_does_not_return(page: Page, client_url: str, host_url: str) -> None:
    speaker = unique_bot("AllowA")
    watcher = unique_bot("AllowB")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, speaker)
    create_named_bot(page, watcher)
    send_message(page, "e2e-consent-browse", speaker)
    card = page.get_by_test_id("consent-card")
    expect(card).to_be_visible(timeout=20_000)
    page.get_by_test_id("ask-option").filter(has_text="Allow once").click()
    expect(card).to_have_attribute("data-status", "answered", timeout=20_000)
    open_chat(page, watcher)
    open_chat(page, speaker)
    expect(page.get_by_test_id("attention-alert").filter(has_text="is asking")).to_have_count(0)
    open_chat(page, watcher)
    expect(page.get_by_test_id("attention-alert").filter(has_text="is asking")).to_have_count(0)


def test_follow_up_after_takeover_starts_a_turn(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Park")
    box = composer(page)
    box.fill("please e2e-park-takeover")
    expect(box).to_have_value("please e2e-park-takeover")
    box.press("Enter")
    expect(page.get_by_test_id("computer-card")).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("typing-indicator")).to_have_count(0)
    expect(page.get_by_test_id("thread-stop")).to_have_count(0)
    send_message(page, "go on")
    expect(
        page.locator('[data-testid="thread-message"][data-role="bot"]').filter(has_text="ok")
    ).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("thread-stop")).to_have_count(0)


def test_takeover_card_shows_reason_and_open_computer(
    page: Page, client_url: str, host_url: str
) -> None:
    from artek_buddy.runtime.scripted import E2E_TAKEOVER_REASON

    name = unique_bot("Card")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name, private=True)
    box = composer(page)
    box.fill("please e2e-park-takeover")
    expect(box).to_have_value("please e2e-park-takeover")
    box.press("Enter")
    card = page.get_by_test_id("computer-card")
    expect(card).to_contain_text(E2E_TAKEOVER_REASON, timeout=8_000)
    expect(page.get_by_test_id("open-computer")).to_be_visible()
    expect(page.get_by_test_id("typing-indicator")).to_have_count(0)
    expect(page.get_by_test_id("thread-stop")).to_have_count(0)
    page.get_by_test_id("open-computer").click()
    expect(page.get_by_label("Close computer")).to_be_visible(timeout=15_000)
    overlay = page.get_by_test_id("computer-overlay")
    overlay.get_by_role("button", name="Take control").click()
    expect(page.get_by_test_id("computer-overlay-holder")).to_be_visible(timeout=8_000)
    overlay.get_by_role("button", name="Release").click()
    page.get_by_label("Close computer").click()
    expect(page.get_by_label("Close computer")).to_have_count(0)
    expect(
        page.locator('[data-testid="thread-message"][data-role="bot"]').filter(
            has_text="continuing after takeover"
        )
    ).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("open-computer")).to_have_count(0)


def test_scripted_image_success_shows_one_card_and_one_generating(
    page: Page, client_url: str, host_url: str
) -> None:
    name = _named(page, client_url, host_url, "ImgOk")
    send_message(page, "please e2e-generate-image", name)
    thread = page.get_by_test_id("thread")
    expect(thread.get_by_test_id("file-card").filter(has_text="fox.png")).to_be_visible(
        timeout=15_000
    )
    expect(thread.get_by_text("Generating…")).to_have_count(1)
    expect(thread.get_by_test_id("file-preview")).to_be_visible()


def test_scripted_image_failure_shows_error_not_hung_or_stopped(
    page: Page, client_url: str, host_url: str
) -> None:
    from artek_buddy.runtime.scripted import E2E_GENERATE_ERROR

    name = _named(page, client_url, host_url, "ImgFail")
    send_message(page, "please e2e-generate-image-fail", name)
    expect(page.get_by_test_id("run-error")).to_contain_text(E2E_GENERATE_ERROR, timeout=15_000)
    expect(page.get_by_test_id("run-error")).not_to_contain_text("Stopped.")
    expect(page.get_by_test_id("file-card")).to_have_count(0)
    expect(page.get_by_test_id("typing-indicator")).to_have_count(0)


def test_user_stop_during_generate_shows_stopped_and_no_later_card(
    page: Page, client_url: str, host_url: str
) -> None:
    name = _named(page, client_url, host_url, "ImgStop")
    box = composer(page)
    box.fill("please e2e-generate-image")
    expect(box).to_have_value("please e2e-generate-image")
    box.press("Enter")
    expect(page.get_by_test_id("thread").get_by_text("Generating…")).to_be_visible(timeout=8_000)
    page.get_by_test_id("thread-stop").click()
    expect(page.get_by_test_id("run-error")).to_contain_text("Stopped.", timeout=15_000)
    page.wait_for_timeout(3_000)
    expect(page.get_by_test_id("file-card")).to_have_count(0)


def test_subagent_stop_while_running(page: Page, client_url: str, host_url: str) -> None:
    from artek_buddy.runtime.scripted import E2E_WORKER_ACK

    name = _named(page, client_url, host_url, "Worker")
    send_message(page, "please e2e-background-worker-chat", name)
    thread = page.get_by_test_id("thread")
    expect(thread.get_by_text(E2E_WORKER_ACK)).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("subagent-card")).to_have_count(0)
    expect(thread.get_by_text("Started Researcher.")).to_have_count(0)
    expect(composer(page)).to_be_enabled()
    page.get_by_test_id("thread-stop").click()
    expect(page.get_by_test_id("run-error")).to_contain_text("Stopped.", timeout=15_000)


def test_background_worker_keeps_composer_and_one_summary(
    page: Page, client_url: str, host_url: str
) -> None:
    from artek_buddy.runtime.scripted import (
        E2E_WORKER_ACK,
        E2E_WORKER_STATUS,
        E2E_WORKER_SUMMARY,
    )

    name = _named(page, client_url, host_url, "BgChat")
    send_message(page, "please e2e-background-worker-chat", name)
    thread = page.get_by_test_id("thread")
    expect(thread.get_by_text(E2E_WORKER_ACK)).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("subagent-card")).to_have_count(0)
    expect(page.get_by_test_id("thread-stop")).to_be_visible()
    expect(composer(page)).to_be_enabled()
    send_message(page, "please e2e-worker-status", name)
    expect(thread.get_by_text(E2E_WORKER_STATUS)).to_be_visible(timeout=8_000)
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_be_visible(timeout=20_000)
    expect(thread.get_by_text(E2E_WORKER_SUMMARY)).to_have_count(1)
    expect(thread.get_by_text("blocked work finished")).to_have_count(0)
    expect(page.get_by_test_id("subagent-card")).to_have_count(0)


def test_takeover_banner_on_other_chat(page: Page, client_url: str, host_url: str) -> None:
    speaker = unique_bot("Need")
    watcher = unique_bot("Idle")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, speaker)
    create_named_bot(page, watcher)
    open_chat(page, speaker)
    box = composer(page)
    box.fill("please e2e-takeover")
    expect(box).to_have_value("please e2e-takeover")
    box.press("Enter")
    open_chat(page, watcher)
    expect(thread_header(page)).to_contain_text(watcher)
    banner = page.get_by_test_id("attention-alert")
    expect(banner).to_contain_text(f"{speaker} needs you", timeout=15_000)
    expect(thread_header(page)).to_contain_text(watcher)
    page.get_by_test_id("attention-dismiss").click()
    expect(banner).to_have_count(0)


def test_takeover_banner_after_park_then_switch(page: Page, client_url: str, host_url: str) -> None:
    speaker = unique_bot("Need")
    watcher = unique_bot("Idle")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, speaker)
    create_named_bot(page, watcher)
    open_chat(page, speaker)
    box = composer(page)
    box.fill("please e2e-takeover")
    expect(box).to_have_value("please e2e-takeover")
    box.press("Enter")
    expect(thread_header(page)).to_contain_text(speaker)
    expect(bot_row(page, speaker)).to_contain_text("waiting_takeover", timeout=15_000)
    expect(page.get_by_test_id("attention-alert")).to_have_count(0)
    open_chat(page, watcher)
    expect(thread_header(page)).to_contain_text(watcher)
    expect(page.get_by_test_id("attention-alert")).to_contain_text(
        f"{speaker} needs you", timeout=15_000
    )


def test_dismiss_needs_you_after_park_then_switch(
    page: Page, client_url: str, host_url: str
) -> None:
    speaker = unique_bot("ParkA")
    watcher = unique_bot("ParkB")
    other = unique_bot("ParkC")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, speaker)
    create_named_bot(page, watcher)
    create_named_bot(page, other)
    open_chat(page, speaker)
    box = composer(page)
    box.fill("please e2e-takeover")
    expect(box).to_have_value("please e2e-takeover")
    box.press("Enter")
    expect(thread_header(page)).to_contain_text(speaker)
    expect(bot_row(page, speaker)).to_contain_text("waiting_takeover", timeout=15_000)
    expect(page.get_by_test_id("attention-alert")).to_have_count(0)
    open_chat(page, watcher)
    expect(thread_header(page)).to_contain_text(watcher)
    banner = page.get_by_test_id("attention-alert")
    expect(banner).to_contain_text(f"{speaker} needs you", timeout=15_000)
    page.get_by_test_id("attention-dismiss").click()
    expect(banner).to_have_count(0)
    expect(thread_header(page)).to_contain_text(watcher)
    open_chat(page, other)
    expect(thread_header(page)).to_contain_text(other)
    expect(page.get_by_test_id("attention-alert")).to_have_count(0)
    open_chat(page, watcher)
    expect(thread_header(page)).to_contain_text(watcher)
    expect(page.get_by_test_id("attention-alert")).to_have_count(0)


def test_dismiss_needs_you_keeps_current_chat(page: Page, client_url: str, host_url: str) -> None:
    speaker = unique_bot("ParkA")
    watcher = unique_bot("ParkB")
    other = unique_bot("ParkC")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, speaker)
    create_named_bot(page, watcher)
    create_named_bot(page, other)
    open_chat(page, speaker)
    box = composer(page)
    box.fill("please e2e-takeover")
    expect(box).to_have_value("please e2e-takeover")
    box.press("Enter")
    open_chat(page, watcher)
    expect(thread_header(page)).to_contain_text(watcher)
    banner = page.get_by_test_id("attention-alert")
    expect(banner).to_contain_text(f"{speaker} needs you", timeout=15_000)
    page.get_by_test_id("attention-dismiss").click()
    expect(banner).to_have_count(0)
    expect(thread_header(page)).to_contain_text(watcher)
    expect(thread_header(page)).not_to_contain_text(speaker)
    expect(thread_header(page)).not_to_contain_text(other)
    expect(composer(page)).to_have_attribute("placeholder", f"Message {watcher}")


def test_deb_background_reply_posts_one_native_notification(
    page: Page, client_url: str, host_url: str
) -> None:
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
    speaker = unique_bot("Native")
    watcher = unique_bot("Watch")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, speaker)
    create_named_bot(page, watcher)
    speaker_id = bot_row(page, speaker).get_attribute("data-bot-id")
    assert speaker_id
    open_chat(page, speaker)
    box = composer(page)
    box.fill("please e2e-slow")
    expect(box).to_have_value("please e2e-slow")
    box.press("Enter")
    open_chat(page, watcher)
    expect(bot_row(page, speaker)).to_contain_text("slow done", timeout=15_000)

    assert len(native_requests) == 1
    assert native_requests[0].post_data_json["title"] == f"{speaker} replied"
    assert native_requests[0].post_data_json["tag"] == f"artek-buddy:{speaker_id}"

    open_chat(page, speaker)
    expect(bot_row(page, speaker).get_by_test_id("unread-dot")).to_have_count(0)
    assert dismiss_requests[-1].post_data_json["tag"] == f"artek-buddy:{speaker_id}"


def test_notify_off_mutes_replied_not_ask(page: Page, client_url: str, host_url: str) -> None:
    speaker = unique_bot("Mute")
    watcher = unique_bot("Hear")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, speaker)
    page.get_by_test_id("thread-pane").get_by_role("button", name="Settings").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible()
    page.get_by_test_id("notify-on-finish").uncheck()
    page.get_by_label("Close settings").click()
    create_named_bot(page, watcher)
    open_chat(page, speaker)
    box = composer(page)
    box.fill("please e2e-slow")
    expect(box).to_have_value("please e2e-slow")
    box.press("Enter")
    open_chat(page, watcher)
    expect(bot_row(page, speaker)).to_contain_text("slow done", timeout=15_000)
    expect(page.get_by_test_id("attention-alert")).to_have_count(0)
    open_chat(page, speaker)
    box = composer(page)
    box.fill("research a city")
    expect(box).to_have_value("research a city")
    box.press("Enter")
    open_chat(page, watcher)
    expect(page.get_by_test_id("attention-alert")).to_contain_text(
        f"{speaker} is asking", timeout=15_000
    )


def test_failed_banner_on_other_chat(page: Page, client_url: str, host_url: str) -> None:
    speaker = unique_bot("Boom")
    watcher = unique_bot("See")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, speaker)
    create_named_bot(page, watcher)
    expect(page.get_by_test_id("attention-alert")).to_have_count(0)
    open_chat(page, speaker)
    box = composer(page)
    box.fill("please e2e-fail-slow")
    expect(box).to_have_value("please e2e-fail-slow")
    box.press("Enter")
    open_chat(page, watcher)
    expect(thread_header(page)).to_contain_text(watcher)
    banner = page.get_by_test_id("attention-alert")
    expect(banner).to_contain_text(f"{speaker} failed", timeout=15_000)
    expect(thread_header(page)).to_contain_text(watcher)
    page.get_by_test_id("attention-dismiss").click()
    expect(banner).to_have_count(0)


def test_offline_send_queues_then_flushes_with_caption(
    page: Page, client_url: str, host_url: str
) -> None:
    name = _named(page, client_url, host_url, "Offline")
    ensure_model(page)
    expect(thread_header(page)).to_contain_text(name)
    parked = "hello while the host is down"
    later = "hello after reconnect"
    cut_host(page)
    box = composer(page)
    box.fill(parked)
    expect(box).to_have_value(parked)
    box.press("Enter")
    expect(page.get_by_test_id("reconnect-banner")).to_be_visible(timeout=8_000)
    bubble = page.locator('[data-testid="thread-message"][data-role="user"]').filter(
        has_text=parked
    )
    expect(bubble).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("queued-pending")).to_contain_text("Waiting for the host")
    expect(page.get_by_test_id("offline-sent-caption")).to_have_count(0)
    expect(box).to_have_value("")
    restore_host(page)
    page.get_by_test_id("reconnect-banner").get_by_role("button", name="Retry connection").click()
    expect(page.get_by_test_id("offline-sent-caption")).to_contain_text(
        "Sent while offline", timeout=20_000
    )
    expect(page.get_by_test_id("queued-pending")).to_have_count(0)
    expect(page.get_by_test_id("reconnect-banner")).to_have_count(0)
    box.fill(later)
    expect(box).to_have_value(later)
    box.press("Enter")
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(has_text=later)
    ).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("offline-sent-caption")).to_have_count(1)


def test_queued_send_shows_pending_then_local_caption(
    page: Page, client_url: str, host_url: str
) -> None:
    name = _named(page, client_url, host_url, "Queued")
    ensure_model(page)
    expect(thread_header(page)).to_contain_text(name)
    parked = "queued while unreachable"
    later = "online after the queue"
    cut_host(page)
    box = composer(page)
    box.fill(parked)
    expect(box).to_have_value(parked)
    box.press("Enter")
    bubble = page.locator('[data-testid="thread-message"][data-role="user"]').filter(
        has_text=parked
    )
    expect(bubble).to_be_visible(timeout=8_000)
    expect(bubble).to_have_attribute("data-queued", "true")
    pending = page.get_by_test_id("queued-pending")
    expect(pending).to_be_visible()
    expect(pending).to_contain_text("Waiting for the host")
    expect(page.get_by_test_id("offline-sent-caption")).to_have_count(0)
    restore_host(page)
    page.get_by_test_id("reconnect-banner").get_by_role("button", name="Retry connection").click()
    caption = page.get_by_test_id("offline-sent-caption")
    expect(caption).to_contain_text("Sent while offline", timeout=20_000)
    expect(caption).to_contain_text("·")
    expect(pending).to_have_count(0)
    box.fill(later)
    expect(box).to_have_value(later)
    box.press("Enter")
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(has_text=later)
    ).to_be_visible(timeout=8_000)
    expect(caption).to_have_count(1)


def test_auth_error_send_does_not_queue(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "NoQueue")
    ensure_model(page)
    expect(thread_header(page)).to_contain_text(name)
    page.route(
        "**/v1/threads/**/messages",
        lambda route: (
            route.fulfill(
                status=401,
                content_type="application/json",
                body='{"detail":"invalid token"}',
            )
            if route.request.method == "POST"
            else route.continue_()
        ),
    )
    box = composer(page)
    box.fill("should not queue")
    expect(box).to_have_value("should not queue")
    box.press("Enter")
    expect(page.get_by_test_id("auth-error")).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("reconnect-banner")).to_have_count(0)
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(
            has_text="should not queue"
        )
    ).to_have_count(0)
    expect(box).to_have_value("should not queue")
