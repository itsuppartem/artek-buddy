from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import bot_row, close_computer_pane, create_named_bot, open_computer_pane, pair_fresh

pytestmark = pytest.mark.live


def test_create_memory_routine_and_settings(
    page: Page,
    client_url: str,
    host_url: str,
) -> None:
    """Memory and routines live in the computer pane; open it after Create."""
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, "CI Team")
    open_computer_pane(page)

    expect(page.get_by_test_id("new-memory")).to_be_visible(timeout=20_000)
    page.get_by_test_id("new-memory").click()
    facts = page.get_by_placeholder("Facts to remember")
    expect(facts).to_be_visible(timeout=20_000)
    facts.fill("CI prefers short answers")
    page.get_by_test_id("memory-save").click()
    expect(page.get_by_test_id("memory-doc").filter(has_text="CI prefers short answers")).to_be_visible(
        timeout=20_000
    )

    page.get_by_test_id("new-routine").click()
    page.get_by_placeholder("Name").fill("Morning")
    page.get_by_placeholder("0 9 * * *").fill("not cron")
    page.get_by_placeholder("Prompt to send").fill("brief me")
    expect(page.get_by_role("button", name="Save")).to_be_disabled()
    page.get_by_placeholder("0 9 * * *").fill("0 9 * * *")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("routine-row")).to_contain_text("Morning", timeout=20_000)

    page.locator('[data-testid="thread-pane"] button').filter(has_text="CI Team").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible(timeout=20_000)
    page.get_by_role("button", name="Edit Profile").click()
    page.get_by_test_id("bot-name-input").fill("CI Team Renamed")
    page.get_by_role("button", name="Save").click()
    expect(bot_row(page, "CI Team Renamed")).to_be_visible(timeout=20_000)
    close_computer_pane(page)
