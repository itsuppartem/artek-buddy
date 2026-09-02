from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import arm_page

pytestmark = pytest.mark.live


def test_pairing_rejects_bad_code(page: Page, client_url: str, host_url: str) -> None:
    arm_page(page)
    page.goto(client_url, timeout=20_000, wait_until="domcontentloaded")
    form = page.get_by_test_id("pairing")
    form.wait_for(timeout=8_000)
    page.get_by_placeholder("https://host.example").fill(host_url)
    page.get_by_placeholder("XXXX-XXXX").fill("ZZZZ-ZZZZ")
    page.get_by_role("button", name="Pair").click()
    expect(page.get_by_test_id("pairing-error")).to_be_visible(timeout=8_000)
