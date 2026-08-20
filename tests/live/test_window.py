from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import (
    arm_page,
    bot_row,
    close_computer_pane,
    create_named_bot,
    open_computer_pane,
    pair_fresh,
    seed_memory,
)

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


def test_pair_create_memory_routine_and_settings(
    page: Page,
    client_url: str,
    host_url: str,
) -> None:
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, "CI Team", close_pane=False)

    # Leftover computers boot and swallow the memory Save click (no POST). Seed
    # through the paired session, remount the pane so the list refreshes.
    # Form Save leftover stays on #32.
    seed_memory(page, "CI prefers short answers")
    close_computer_pane(page)
    open_computer_pane(page)
    expect(page.get_by_test_id("memory-doc")).to_contain_text(
        "CI prefers short answers",
        timeout=20_000,
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


def test_unpair_returns_to_pairing(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    close_computer_pane(page)
    # Leftover bots auto-boot noVNC. reload/domcontentloaded then sits on 502s.
    page.evaluate("() => window.stop()")
    page.route("**/novnc/**", lambda route: route.abort())
    page.evaluate(
        """() => fetch('/local/unpair', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})"""
    )
    page.goto(client_url, timeout=15_000, wait_until="commit")
    expect(page.get_by_test_id("pairing")).to_be_visible(timeout=20_000)
