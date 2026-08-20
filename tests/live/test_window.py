from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import arm_page, bot_row, create_named_bot, pair_fresh, reset_pairing

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
    create_named_bot(page, "CI Team", private=False, close_computer=False)

    # Memory sits in the computer pane Create just opened. Do not toggle
    # Agent computer — that closes an already-open pane and reboots noVNC.
    expect(page.get_by_test_id("new-memory")).to_be_visible(timeout=20_000)
    page.get_by_test_id("new-memory").click(timeout=5_000)
    page.get_by_placeholder("Facts to remember").fill("CI prefers short answers")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("memory-doc")).to_contain_text(
        "CI prefers short answers",
        timeout=8_000,
    )

    page.get_by_test_id("new-routine").click(timeout=5_000)
    page.get_by_placeholder("Name").fill("Morning")
    page.get_by_placeholder("0 9 * * *").fill("not cron")
    page.get_by_placeholder("Prompt to send").fill("brief me")
    expect(page.get_by_role("button", name="Save")).to_be_disabled()
    page.get_by_placeholder("0 9 * * *").fill("0 9 * * *")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("routine-row")).to_contain_text("Morning", timeout=8_000)

    page.locator('[data-testid="thread-pane"] button').filter(has_text="CI Team").click(timeout=5_000)
    expect(page.get_by_text("Bot Settings")).to_be_visible(timeout=8_000)
    page.get_by_role("button", name="Edit Profile").click()
    page.get_by_test_id("bot-name-input").fill("CI Team Renamed")
    page.get_by_role("button", name="Save").click()
    expect(bot_row(page, "CI Team Renamed")).to_be_visible(timeout=8_000)


def test_unpair_returns_to_pairing(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=8_000)
    # HTTP unpair is bounded. page.evaluate(fetch) + goto(load) can sit in CDP forever.
    reset_pairing(client_url)
    page.goto(client_url, timeout=10_000, wait_until="domcontentloaded")
    expect(page.get_by_test_id("pairing")).to_be_visible(timeout=8_000)
