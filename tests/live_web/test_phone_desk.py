from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import unique_bot
from tests.live_web.helpers import create_named_bot_phone, open_phone_tab, pair_host_page

pytestmark = pytest.mark.live


def test_host_page_desktop_overlay_is_a_phone_pad(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("PadWeb"))
    open_phone_tab(page, "desk")
    page.get_by_test_id("computer-start").click()
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
    expect(page.get_by_test_id("phone-desk-keys")).to_be_visible()
    expect(page.get_by_test_id("phone-desk-key-row")).to_be_visible()
    page.set_viewport_size({"width": 812, "height": 375})
    expect(overlay).to_be_visible()
    expect(overlay.get_by_test_id("phone-desk-pad")).to_be_visible()
    wide = overlay.bounding_box()
    assert wide is not None
    assert wide["width"] >= 800
