from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import pair_fresh

pytestmark = pytest.mark.live


def test_pairing_rejects_bad_code(page: Page, client_url: str, host_url: str) -> None:
    page.goto(client_url)
    form = page.get_by_test_id("pairing")
    form.wait_for()
    page.get_by_placeholder("https://host.example").fill(host_url)
    page.get_by_placeholder("XXXX-XXXX").fill("ZZZZ-ZZZZ")
    page.get_by_role("button", name="Pair").click()
    expect(page.get_by_test_id("pairing-error")).to_be_visible()


def test_pair_create_memory_routine_and_settings(
    page: Page,
    client_url: str,
    host_url: str,
) -> None:
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_test_id("empty-bots")).to_be_visible(timeout=20_000)

    page.get_by_role("button", name="Create bot", exact=True).click()
    page.get_by_placeholder("Name this bot").fill("CI Team")
    page.get_by_role("button", name="Create", exact=True).click()
    expect(page.get_by_test_id("bot-row")).to_contain_text("CI Team", timeout=20_000)

    page.get_by_test_id("new-memory").click()
    page.get_by_placeholder("Facts to remember").fill("CI prefers short answers")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("memory-doc")).to_contain_text("CI prefers short answers")

    page.get_by_test_id("new-routine").click()
    page.get_by_placeholder("Name").fill("Morning")
    page.get_by_placeholder("0 9 * * *").fill("not cron")
    page.get_by_placeholder("Prompt to send").fill("brief me")
    expect(page.get_by_role("button", name="Save")).to_be_disabled()
    page.get_by_placeholder("0 9 * * *").fill("0 9 * * *")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("routine-row")).to_contain_text("Morning")

    page.locator('[data-testid="thread-pane"] button').filter(has_text="CI Team").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible()
    page.get_by_role("button", name="Edit Profile").click()
    page.get_by_test_id("bot-name-input").fill("CI Team Renamed")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("bot-row")).to_contain_text("CI Team Renamed")


def test_unpair_returns_to_pairing(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    page.evaluate(
        """() => fetch('/local/unpair', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})"""
    )
    page.goto(client_url)
    expect(page.get_by_test_id("pairing")).to_be_visible()
