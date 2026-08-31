from __future__ import annotations

import base64

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import composer, unique_bot
from tests.live_web.helpers import create_named_bot_phone, pair_host_page, send_message_phone

pytestmark = pytest.mark.live

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_host_page_paste_screenshot_attaches_chip(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("PhPaste"))
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


def test_host_page_scripted_file_card_and_image_preview(page: Page, host_url: str) -> None:
    local_cuts: list[str] = []

    def track(request) -> None:
        url = request.url
        if (
            "/local/owner-" in url
            or "/local/save-artifact" in url
            or "/local/save-home-file" in url
        ):
            local_cuts.append(url)

    page.on("request", track)
    name = unique_bot("PhFile")
    pair_host_page(page, host_url)
    create_named_bot_phone(page, name)
    send_message_phone(page, "please e2e-send-file")
    card = page.get_by_test_id("file-card")
    expect(card).to_contain_text("notes.txt", timeout=15_000)
    with page.expect_download() as download:
        card.get_by_role("button", name="Download").click()
    assert download.value.suggested_filename.endswith("notes.txt")
    expect(page.get_by_test_id("file-saved")).to_have_count(0)
    send_message_phone(page, "please e2e-send-image")
    image = page.get_by_test_id("file-card").filter(has_text="shot.png")
    expect(image).to_be_visible(timeout=15_000)
    expect(image.get_by_test_id("file-preview")).to_be_visible()
    assert local_cuts == []
