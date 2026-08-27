from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import create_named_bot, open_settings, pair_fresh, unique_bot

pytestmark = pytest.mark.live


def test_create_team_default_and_private(page: Page, client_url: str, host_url: str) -> None:
    team = unique_bot("Team")
    private = unique_bot("Priv")
    pair_fresh(page, client_url, host_url)
    page.get_by_role("button", name="New bot").click()
    page.get_by_placeholder("Name this bot").fill(team)
    expect(page.get_by_placeholder("Describe what this bot does")).to_have_count(0)
    page.get_by_placeholder("e.g. Code Reviewer").fill("team desk")
    page.get_by_placeholder("What this bot is for").fill("shared work")
    expect(page.get_by_test_id("computer-mode-hint")).to_contain_text("Team bots share")
    page.get_by_role("button", name="Create", exact=True).click()
    expect(page.get_by_placeholder("Name this bot")).to_have_count(0, timeout=20_000)
    create_named_bot(page, private, private=True)
    open_settings(page, team)
    expect(page.get_by_text("Computer: Team")).to_be_visible()
    expect(
        page.get_by_text("Reset wipes the shared Team desktop for every Team bot.")
    ).to_be_visible()
    page.get_by_label("Close settings").click()
    open_settings(page, private)
    expect(page.get_by_text("Computer: Private")).to_be_visible()
    expect(page.get_by_text("Reset wipes the shared Team desktop")).to_have_count(0)


def test_settings_edit_notify_reset_cancel_delete(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("Set")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name, title="old title", description="old desc", private=True)
    open_settings(page, name)
    page.get_by_test_id("computer-reset").click()
    expect(page.get_by_text("Erase this computer’s home?")).to_be_visible()
    page.get_by_role("button", name="Cancel").click()
    expect(page.get_by_text("Erase this computer’s home?")).to_have_count(0)
    page.get_by_role("button", name="Edit profile").click()
    page.get_by_placeholder("e.g. Code Reviewer").fill("new title")
    page.get_by_placeholder("What this bot is for").fill("new desc")
    expect(page.get_by_label("Instructions (Prompt)")).to_have_count(0)
    expect(page.get_by_placeholder("Standing orders for this bot")).to_be_visible()
    page.get_by_label("Instructions").fill("be terse")
    page.get_by_test_id("computer-mode-team").click()
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Computer: Team")).to_be_visible(timeout=8_000)
    box = page.get_by_test_id("notify-on-finish")
    expect(box).to_be_checked()
    box.uncheck()
    page.get_by_label("Close settings").click()
    open_settings(page, name)
    expect(page.get_by_test_id("notify-on-finish")).not_to_be_checked()
    page.get_by_role("button", name="Delete chat…").click()
    expect(page.get_by_text("Delete this chat and its history?")).to_be_visible()
    page.get_by_text("Also purge bot-specific memories").click()
    page.get_by_role("button", name="Cancel").click()
    expect(page.get_by_text("Delete this chat and its history?")).to_have_count(0)
    page.get_by_role("button", name="Delete chat…").click()
    page.get_by_role("button", name="Delete", exact=True).click()
    expect(page.get_by_test_id("bot-row").filter(has_text=name)).to_have_count(0, timeout=8_000)


def test_settings_title_keeps_value_after_blur_and_save(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("Ttl")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name, private=True)
    open_settings(page, name)
    page.get_by_role("button", name="Edit profile").click()
    title = page.get_by_test_id("bot-title-input")
    title.fill("QA Helper")
    expect(title).to_have_value("QA Helper")
    title.blur()
    with page.expect_response(
        lambda response: response.request.method == "GET"
        and "/v1/bots" in response.url
        and response.ok
    ):
        page.get_by_test_id("notify-on-finish").uncheck()
    expect(title).to_have_value("QA Helper")
    page.get_by_test_id("settings-save").click()
    expect(page.get_by_role("button", name="Saved")).to_be_visible(timeout=8_000)
    expect(page.get_by_role("button", name="Edit profile")).to_be_visible(timeout=8_000)
    expect(page.get_by_text("QA Helper", exact=True)).to_be_visible()
    page.get_by_role("button", name="Edit profile").click()
    expect(page.get_by_test_id("bot-title-input")).to_have_value("QA Helper")
