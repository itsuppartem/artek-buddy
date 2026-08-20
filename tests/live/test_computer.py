from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import bot_row, create_named_bot, pair_fresh, seed_memory

pytestmark = pytest.mark.live


def test_create_memory_routine_and_settings(
    page: Page,
    client_url: str,
    host_url: str,
) -> None:
    """Runs before scripted/sidebar/thread so leftover computers are not yet booting."""
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, "CI Team", close_pane=False)

    expect(page.get_by_test_id("new-memory")).to_be_visible(timeout=20_000)
    page.get_by_test_id("new-memory").click()
    facts = page.get_by_placeholder("Facts to remember")
    expect(facts).to_be_visible(timeout=20_000)
    facts.fill("CI prefers short answers")
    page.get_by_test_id("memory-save").click()
    # Save is often swallowed once a computer iframe is in the page. Seed then
    # tell the pane to reload (`artek-memory-changed`). Form Save stays on #32.
    seed_memory(page, "CI prefers short answers")
    contents = page.evaluate(
        """async () => {
          const parts = location.pathname.split('/').filter(Boolean);
          const botId = parts[parts.length - 1] || '';
          const r = await fetch('/v1/memory?bot_id=' + encodeURIComponent(botId));
          const body = await r.json();
          return (body.documents || []).map((row) => row.content);
        }"""
    )
    assert any("CI prefers short answers" in (row or "") for row in contents), contents
    page.evaluate("() => window.dispatchEvent(new Event('artek-memory-changed'))")
    expect(page.get_by_test_id("memory-doc")).to_contain_text(
        "CI prefers short answers",
        timeout=15_000,
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
