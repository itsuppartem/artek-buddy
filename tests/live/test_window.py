from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import arm_page, create_named_bot, pair_fresh, unique_bot

pytestmark = pytest.mark.live


def test_pairing_rejects_bad_code(page: Page, client_url: str, host_url: str) -> None:
    arm_page(page)
    page.goto(client_url, timeout=20_000, wait_until="domcontentloaded")
    form = page.get_by_test_id("pairing")
    form.wait_for(timeout=8_000)
    form.get_by_text("Pairing options", exact=True).click()
    page.get_by_placeholder("https://host.example").fill(host_url)
    page.get_by_placeholder("XXXX-XXXX").fill("ZZZZ-ZZZZ")
    page.get_by_role("button", name="Pair").click()
    expect(page.get_by_test_id("pairing-error")).to_be_visible(timeout=8_000)


def test_desktop_panes_resize_by_drag(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("Resize")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)

    rack = page.locator('[data-shell="rack"]')
    left = page.get_by_role("separator", name="Resize work list")
    before = rack.bounding_box()
    divider = left.bounding_box()
    assert before is not None
    assert divider is not None
    page.mouse.move(divider["x"] + 4, divider["y"] + 80)
    page.mouse.down()
    page.mouse.move(divider["x"] + 44, divider["y"] + 80, steps=4)
    page.mouse.up()
    after = rack.bounding_box()
    assert after is not None
    assert after["width"] >= before["width"] + 35

    page.get_by_test_id("workspace-rail").get_by_role("button", name="Library").click()
    hatch = page.locator('[data-shell="hatch"]')
    right = page.get_by_role("separator", name="Resize side panel")
    before = hatch.bounding_box()
    divider = right.bounding_box()
    assert before is not None
    assert divider is not None
    page.mouse.move(divider["x"] + 4, divider["y"] + 80)
    page.mouse.down()
    page.mouse.move(divider["x"] + 44, divider["y"] + 80, steps=4)
    page.mouse.up()
    after = hatch.bounding_box()
    assert after is not None
    assert after["width"] <= before["width"] - 35
    expect(page.get_by_test_id("thread-pane")).to_be_visible()


def test_appearance_follows_system_and_persists_override(
    page: Page, client_url: str, host_url: str
) -> None:
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, unique_bot("Theme"))
    page.emulate_media(color_scheme="dark")

    rail = page.get_by_test_id("workspace-rail")
    rail.get_by_role("button", name="Library").click()
    picker = page.get_by_test_id("theme-picker")
    expect(picker.get_by_role("radio", name="System")).to_be_checked()
    expect(page.locator("body")).to_have_css("background-color", "rgb(13, 23, 39)")

    picker.get_by_text("Light", exact=True).click()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    expect(page.locator("body")).to_have_css("background-color", "rgb(244, 247, 251)")

    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    page.get_by_test_id("workspace-rail").get_by_role("button", name="Library").click()
    picker = page.get_by_test_id("theme-picker")
    expect(picker.get_by_role("radio", name="Light")).to_be_checked()

    picker.get_by_text("System", exact=True).click()
    expect(page.locator("body")).to_have_css("background-color", "rgb(13, 23, 39)")
    page.emulate_media(color_scheme="light")
    expect(page.locator("body")).to_have_css("background-color", "rgb(244, 247, 251)")
