from __future__ import annotations

import time

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import unique_bot
from tests.live_web.helpers import create_named_bot_phone, open_phone_tab, pair_host_page

pytestmark = pytest.mark.live


def test_host_page_desktop_overlay_is_a_phone_pad(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("PadWeb"), private=True)
    open_phone_tab(page, "desk")
    page.get_by_test_id("computer-start").click()
    expect(page.get_by_test_id("computer-state")).to_have_attribute(
        "data-state", "running", timeout=20_000
    )
    expect(page.get_by_test_id("computer-overlay")).to_have_count(0)
    page.get_by_role("button", name="Take control").click()
    overlay = page.get_by_test_id("computer-overlay")
    expect(overlay).to_be_visible(timeout=20_000)
    expect(overlay).to_have_attribute("data-phone-desk", "1")
    expect(overlay.get_by_test_id("phone-desk-pad")).to_be_visible()
    expect(overlay.get_by_test_id("phone-desk-keyboard")).to_be_visible()
    box = overlay.bounding_box()
    assert box is not None
    assert box["width"] <= 375
    keys = overlay.get_by_test_id("phone-desk-keyboard")
    key_box = keys.bounding_box()
    assert key_box is not None
    assert key_box["x"] + key_box["width"] <= 376
    keys.click()
    expect(page.get_by_test_id("phone-desk-key-row")).to_be_visible()
    field = page.get_by_role("textbox", name="Type on the desktop")
    expect(field).to_be_visible()
    field_box = field.bounding_box()
    assert field_box is not None
    assert field_box["height"] >= 40
    expect(page.get_by_role("button", name="Enter", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Bksp", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Del", exact=True)).to_be_visible()
    screen = overlay.get_by_test_id("computer-overlay-screen").bounding_box()
    pad = overlay.get_by_test_id("phone-desk-pad").bounding_box()
    assert screen is not None
    assert pad is not None
    assert abs(pad["y"] - screen["y"]) <= 2
    assert abs(pad["height"] - screen["height"]) <= 2
    page.set_viewport_size({"width": 812, "height": 375})
    expect(overlay).to_be_visible()
    expect(overlay.get_by_test_id("phone-desk-pad")).to_be_visible()
    wide = overlay.bounding_box()
    assert wide is not None
    assert wide["width"] >= 800
    page.get_by_label("Close computer").click()
    expect(page.get_by_test_id("computer-overlay")).to_have_count(0)
    expect(page.get_by_test_id("phone-tab-chat")).to_have_attribute("aria-current", "page")


def _controlled_phone_overlay(page: Page, host_url: str, bot: str):
    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot(bot), private=True)
    open_phone_tab(page, "desk")
    page.get_by_test_id("computer-start").click()
    expect(page.get_by_test_id("computer-state")).to_have_attribute(
        "data-state", "running", timeout=20_000
    )
    page.get_by_role("button", name="Take control").click()
    overlay = page.get_by_test_id("computer-overlay")
    expect(overlay).to_be_visible(timeout=20_000)
    expect(overlay.get_by_role("button", name="Release")).to_be_visible()
    return overlay


def _drag(page: Page, box: dict[str, float], dx: float, dy: float) -> None:
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y + dy, steps=8)
    page.mouse.up()


def test_phone_pad_drag_keeps_control_and_keys_are_tappable(page: Page, host_url: str) -> None:
    overlay = _controlled_phone_overlay(page, host_url, "PadHold")
    pad = overlay.get_by_test_id("phone-desk-pad")
    hint = overlay.locator(".phone-desk-hint")
    expect(hint).to_be_visible()
    expect(hint).to_have_css("user-select", "none")

    pad_box = pad.bounding_box()
    assert pad_box is not None
    _drag(page, pad_box, 48, 28)
    pad.click()
    expect(overlay.get_by_role("button", name="Release")).to_be_visible()
    expect(overlay.get_by_role("button", name="Take control")).to_have_count(0)
    expect(overlay.get_by_test_id("computer-overlay-holder")).to_be_visible()

    hint_box = hint.bounding_box()
    assert hint_box is not None
    page.mouse.move(hint_box["x"] + 8, hint_box["y"] + hint_box["height"] / 2)
    page.mouse.down()
    page.mouse.move(
        hint_box["x"] + min(hint_box["width"] - 8, 220),
        hint_box["y"] + hint_box["height"] / 2,
        steps=10,
    )
    page.mouse.up()
    selected = page.evaluate("() => document.getSelection()?.toString() ?? ''")
    assert "Turn the phone" not in selected
    expect(overlay.get_by_role("button", name="Release")).to_be_visible()

    overlay.get_by_test_id("phone-desk-keyboard").click()
    field = overlay.get_by_role("textbox", name="Type on the desktop")
    field.click()
    expect(field).to_be_focused()
    expect(overlay.get_by_role("button", name="Release")).to_be_visible()
    expect(overlay.get_by_role("button", name="Take control")).to_have_count(0)


def test_phone_desk_input_updates_within_seconds(page: Page, host_url: str) -> None:
    overlay = _controlled_phone_overlay(page, host_url, "DeskFast")
    overlay.get_by_test_id("phone-desk-keyboard").click()
    field = overlay.get_by_role("textbox", name="Type on the desktop")
    field.click()
    hello_at: list[float] = []
    input_at: list[float] = []

    def on_response(response) -> None:
        if "/input" not in response.url or response.request.method != "POST" or not response.ok:
            return
        now = time.monotonic()
        input_at.append(now)
        body = response.request.post_data or ""
        if "hello" in body:
            hello_at.append(now)

    page.on("response", on_response)
    started = time.monotonic()
    field.fill("hello")
    expect(field).to_have_value("hello")
    deadline = started + 5.0
    while time.monotonic() < deadline and not hello_at:
        page.wait_for_timeout(50)
    assert hello_at, "typed hello never reached POST /v1/computer/.../input"
    assert hello_at[-1] - started < 5.0, (
        f"desk input took {hello_at[-1] - started:.1f}s; stall over ~5s is a fail"
    )
    expect(overlay.get_by_role("button", name="Release")).to_be_visible(timeout=5_000)
    expect(overlay.get_by_test_id("phone-desk-pad")).to_be_visible()
    pad_box = overlay.get_by_test_id("phone-desk-pad").bounding_box()
    assert pad_box is not None
    before_drag = len(input_at)
    drag_started = time.monotonic()
    _drag(page, pad_box, 40, 24)
    while time.monotonic() < drag_started + 5.0 and len(input_at) == before_drag:
        page.wait_for_timeout(50)
    drag_elapsed = time.monotonic() - drag_started
    expect(overlay.get_by_role("button", name="Release")).to_be_visible(timeout=5_000)
    assert drag_elapsed < 5.0, f"pad drag input took {drag_elapsed:.1f}s; stall over ~5s is a fail"
