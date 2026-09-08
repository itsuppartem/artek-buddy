from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import unique_bot
from tests.live_web.helpers import (
    create_named_bot_phone,
    expect_bot_in_chats,
    open_phone_tab,
    pair_host_page,
)

pytestmark = pytest.mark.live


def _above_phone_nav(page: Page, target) -> None:
    box = target.bounding_box()
    nav = page.get_by_test_id("phone-nav").bounding_box()
    assert box is not None and nav is not None
    assert box["y"] + box["height"] <= nav["y"] + 2


def test_phone_today_scrolls_ready_and_routines_above_nav(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    today = page.get_by_test_id("today-view")
    expect(today).to_be_visible()
    ready = page.get_by_role("heading", name="Ready for you")
    routines = page.get_by_role("button", name="Open routines")
    metrics = today.evaluate("el => ({sh: el.scrollHeight, ch: el.clientHeight})")
    today_box = today.bounding_box()
    routines_box = routines.bounding_box()
    assert today_box is not None and routines_box is not None
    below_fold = routines_box["y"] + 8 > today_box["y"] + today_box["height"]
    assert metrics["sh"] > metrics["ch"] or below_fold
    ready.scroll_into_view_if_needed()
    expect(ready).to_be_in_viewport()
    _above_phone_nav(page, ready)
    routines.scroll_into_view_if_needed()
    expect(routines).to_be_in_viewport()
    _above_phone_nav(page, routines)


def test_phone_more_scrolls_library_profile_into_view(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    open_phone_tab(page, "more")
    expect(page.get_by_test_id("library-pane")).to_be_visible(timeout=8_000)
    hatch = page.locator('[data-shell="hatch"] .ab-scroll')
    expect(hatch).to_be_visible()
    profile = page.get_by_test_id("library-open-settings")
    metrics = hatch.evaluate("el => ({sh: el.scrollHeight, ch: el.clientHeight})")
    if metrics["sh"] <= metrics["ch"]:
        page.add_style_tag(content='[data-testid="library-pane"] { padding-bottom: 720px; }')
        metrics = hatch.evaluate("el => ({sh: el.scrollHeight, ch: el.clientHeight})")
    assert metrics["sh"] > metrics["ch"]
    profile.scroll_into_view_if_needed()
    expect(profile).to_be_in_viewport()
    _above_phone_nav(page, profile)


def test_phone_chats_inbox_scrolls_without_sliding_under_nav(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    names = [unique_bot(f"Rack{i}") for i in range(4)]
    for name in names:
        create_named_bot_phone(page, name)
    open_phone_tab(page, "chats")
    page.add_style_tag(content='[data-testid="bot-row"] { min-height: 160px !important; }')
    scroller = page.locator('[data-shell="rack"] > .ab-scroll')
    expect(scroller).to_be_visible()
    before = scroller.evaluate("el => el.scrollTop")
    scroller.evaluate("el => { el.scrollTop = 240; }")
    after = scroller.evaluate("el => el.scrollTop")
    assert after > before
    expect(page.get_by_label("Search inbox")).to_be_visible()
    expect_bot_in_chats(page, names[0])


def test_phone_nav_sits_on_viewport_bottom_with_inset(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    page.add_style_tag(content="[data-phone-shell='1'] { --phone-safe-bottom: 34px; }")
    nav = page.get_by_test_id("phone-nav")
    expect(nav).to_be_visible()
    nav_box = nav.bounding_box()
    vp = page.viewport_size
    assert nav_box is not None and vp is not None
    assert abs(nav_box["y"] + nav_box["height"] - vp["height"]) <= 2
    buttons = nav.get_by_role("button")
    assert buttons.count() >= 4
    for index in range(buttons.count()):
        box = buttons.nth(index).bounding_box()
        assert box is not None
        assert box["height"] >= 44
