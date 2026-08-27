from __future__ import annotations

import json
import re
import uuid

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    bot_row,
    close_computer_pane,
    create_named_bot,
    open_chat,
    open_computer_pane,
    open_settings,
    pair_fresh,
    send_message,
    unique_bot,
)

pytestmark = pytest.mark.live


def test_create_memory_routine_and_settings(
    page: Page,
    client_url: str,
    host_url: str,
) -> None:
    name = unique_bot("Mem")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    open_computer_pane(page)
    expect(page.get_by_test_id("computer-start")).to_be_visible()
    expect(page.get_by_text("Offline • Click to start")).to_be_visible()

    expect(page.get_by_test_id("new-memory")).to_be_visible(timeout=8_000)
    page.get_by_test_id("new-memory").click()
    page.get_by_role("button", name="This bot").click()
    facts = page.get_by_placeholder("Facts to remember")
    expect(facts).to_be_visible(timeout=8_000)
    facts.fill("CI prefers short answers")
    page.get_by_test_id("memory-save").click()
    expect(page.get_by_role("button", name="Saved")).to_be_visible(timeout=8_000)
    doc = page.get_by_test_id("memory-doc").filter(has_text="CI prefers short answers")
    expect(doc).to_be_visible(timeout=8_000)
    expect(doc).to_contain_text("this bot")

    expect(page.get_by_test_id("new-memory")).to_be_visible(timeout=8_000)
    doc.get_by_role("button", name="Edit").click()
    doc.locator("textarea").fill("CI prefers terse answers")
    doc.get_by_role("button", name="Save").click()
    expect(
        page.get_by_test_id("memory-doc").filter(has_text="CI prefers terse answers")
    ).to_be_visible(timeout=8_000)

    page.get_by_test_id("new-memory").click()
    page.get_by_role("button", name="Shared").click()
    page.get_by_placeholder("Facts to remember").fill("Shared house rule")
    page.get_by_test_id("memory-save").click()
    expect(page.get_by_role("button", name="Saved")).to_be_visible(timeout=8_000)
    shared = page.get_by_test_id("memory-doc").filter(has_text="Shared house rule")
    expect(shared).to_be_visible(timeout=8_000)
    expect(shared).to_contain_text("shared")

    expect(page.get_by_test_id("new-memory")).to_be_visible(timeout=8_000)

    with page.expect_download() as download:
        page.get_by_role("button", name="Export").click()
    assert download.value.suggested_filename.endswith(".md")

    shared.get_by_role("button", name="Outdated").click()
    expect(shared).to_have_count(0)

    page.get_by_test_id("new-routine").click()
    page.get_by_placeholder("Name").fill("Morning")
    page.get_by_placeholder("0 9 * * *").fill("not cron")
    page.get_by_placeholder("Prompt to send").fill("brief me")
    expect(page.get_by_role("button", name="Save")).to_be_disabled()
    page.get_by_placeholder("0 9 * * *").fill("0 9 * * *")
    page.get_by_role("button", name="Save").click()
    row = page.get_by_test_id("routine-row")
    expect(row).to_contain_text("Morning", timeout=8_000)
    row.get_by_role("button", name="on").click()
    expect(row).to_contain_text("paused")
    row.get_by_role("button", name="off").click()
    row.get_by_role("button", name="Run").click()
    expect(page.get_by_text("Routine started")).to_be_visible(timeout=8_000)

    open_settings(page, name)
    page.get_by_role("button", name="Edit profile").click()
    renamed = f"{name} Renamed"
    page.get_by_test_id("bot-name-input").fill(renamed)
    page.get_by_role("button", name="Save").click()
    expect(bot_row(page, renamed)).to_be_visible(timeout=8_000)
    close_computer_pane(page)


def test_routine_survives_reload(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("Cron")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    open_computer_pane(page)
    page.get_by_test_id("new-routine").click()
    page.get_by_placeholder("Name").fill("Stay")
    page.get_by_placeholder("Prompt to send").fill("still here")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_test_id("routine-row")).to_contain_text("Stay", timeout=8_000)
    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    open_chat(page, name)
    open_computer_pane(page)
    expect(page.get_by_test_id("routine-row")).to_contain_text("Stay", timeout=8_000)
    page.get_by_test_id("routine-row").get_by_role("button", name="Delete").click()
    expect(page.get_by_test_id("routine-row")).to_have_count(0)


def test_offline_click_to_start_is_view_only(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("Glance")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name, private=True)
    open_computer_pane(page)
    expect(page.get_by_test_id("computer-state")).to_have_attribute("data-state", "offline")
    page.get_by_role("button", name="Settings").last.click()
    expect(page.get_by_text("Bot Settings")).to_be_visible()
    expect(page.get_by_test_id("computer-power-state")).to_contain_text("Offline")
    page.get_by_label("Close settings").click()
    expect(page.get_by_test_id("computer-state")).to_have_attribute("data-state", "offline")
    expect(page.get_by_text("Offline • Click to start")).to_be_visible()
    page.get_by_test_id("computer-start").click()
    expect(page.get_by_test_id("computer-state")).to_have_attribute(
        "data-state", "running", timeout=15_000
    )
    expect(page.get_by_test_id("computer-running")).to_be_visible()
    expect(page.get_by_test_id("computer-overlay")).to_have_count(0)
    expect(page.get_by_label("Close computer")).to_have_count(0)
    expect(page.get_by_test_id("computer-label")).not_to_contain_text("You have control")
    expect(page.get_by_role("button", name="Take control")).to_be_enabled()
    expect(page.get_by_text("Offline • Click to start")).to_have_count(0)


def test_computer_pane_start_and_close(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("Box")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name, private=True)
    open_computer_pane(page)
    label = page.get_by_test_id("computer-label")
    expect(label).to_have_attribute("data-mode", "dedicated")
    expect(label).to_contain_text(name)
    expect(page.get_by_test_id("computer-state")).to_have_attribute("data-state", "offline")
    page.get_by_test_id("computer-start").click()
    expect(page.get_by_test_id("computer-state")).to_have_attribute(
        "data-state", "running", timeout=15_000
    )
    expect(page.get_by_label("Close computer")).to_have_count(0)
    expect(page.get_by_test_id("computer-running")).to_be_visible()
    page.get_by_role("button", name="Settings").last.click()
    expect(page.get_by_text("Bot Settings")).to_be_visible()
    expect(page.get_by_test_id("computer-power-state")).to_contain_text("Running")
    page.get_by_test_id("computer-stop").click()
    expect(page.get_by_test_id("computer-power-state")).to_contain_text("Sleeping", timeout=8_000)
    page.get_by_test_id("computer-restart").click()
    expect(page.get_by_test_id("computer-power-state")).to_contain_text("Running", timeout=15_000)
    page.get_by_label("Close settings").click()
    page.get_by_title("Close panel").click()
    expect(page.get_by_test_id("new-memory")).to_have_count(0)


def test_team_busy_shows_other_bot(page: Page, client_url: str, host_url: str) -> None:
    alpha = unique_bot("Hold")
    bravo = unique_bot("Wait")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, alpha)
    create_named_bot(page, bravo)
    open_chat(page, alpha)
    open_computer_pane(page)
    page.get_by_test_id("computer-start").click()
    expect(page.get_by_test_id("computer-state")).to_have_attribute(
        "data-state", "running", timeout=15_000
    )
    expect(page.get_by_label("Close computer")).to_have_count(0)
    page.get_by_title("Close panel").click()
    open_chat(page, bravo)
    open_computer_pane(page)
    expect(page.get_by_text(f"{alpha} is using the computer")).to_be_visible(timeout=8_000)
    expect(page.get_by_role("button", name="Take control")).to_be_disabled()
    expect(page.get_by_test_id("computer-start")).to_be_disabled()
    page.get_by_role("button", name="Settings").last.click()
    expect(page.get_by_text(f"{alpha} is using this computer.")).to_be_visible()
    expect(page.get_by_test_id("computer-restart")).to_be_disabled()
    expect(page.get_by_test_id("computer-stop")).to_be_disabled()
    expect(page.get_by_test_id("computer-reset")).to_be_disabled()


def test_computer_pane_stays_open_after_settings_release_and_create(
    page: Page,
    client_url: str,
    host_url: str,
) -> None:
    first = unique_bot("Stay")
    second = unique_bot("Next")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, first, private=True)
    open_computer_pane(page)
    expect(page.get_by_test_id("new-memory")).to_be_visible()
    page.get_by_role("button", name="Settings").last.click()
    expect(page.get_by_text("Bot Settings")).to_be_visible()
    page.get_by_label("Close settings").click()
    expect(page.get_by_test_id("new-memory")).to_be_visible()
    page.get_by_test_id("computer-start").click()
    expect(page.get_by_test_id("computer-state")).to_have_attribute(
        "data-state", "running", timeout=15_000
    )
    expect(page.get_by_label("Close computer")).to_have_count(0)
    page.get_by_role("button", name="Take control").click()
    expect(page.get_by_label("Close computer")).to_be_visible(timeout=15_000)
    page.get_by_label("Close computer").click()
    page.get_by_role("button", name="Release").click()
    expect(page.get_by_test_id("new-memory")).to_be_visible()
    create_named_bot(page, second, private=True)
    expect(page.get_by_test_id("new-memory")).to_be_visible()
    expect(page.get_by_test_id("computer-label")).to_be_visible()


def test_computer_boot_error_shows_failed(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("Err")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name, private=True)
    page.route(
        "**/v1/computer/*/boot",
        lambda route: route.fulfill(
            status=500, content_type="application/json", body='{"detail":"boom"}'
        ),
    )
    open_computer_pane(page)
    page.get_by_test_id("computer-start").click()
    expect(page.get_by_text("boom").or_(page.get_by_text("Failed to start"))).to_be_visible(
        timeout=8_000
    )


def test_preview_click_opens_screen_without_control(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("Prev")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name, private=True)
    open_computer_pane(page)
    page.get_by_test_id("computer-start").click()
    expect(page.get_by_test_id("computer-state")).to_have_attribute(
        "data-state", "running", timeout=15_000
    )
    expect(page.get_by_label("Close computer")).to_have_count(0)
    expect(page.get_by_test_id("computer-running")).to_be_visible()
    expect(page.get_by_test_id("computer-label")).not_to_contain_text("You have control")
    page.get_by_test_id("computer-preview").click()
    expect(page.get_by_label("Close computer")).to_be_visible(timeout=8_000)
    expect(page.get_by_text("You have control")).to_have_count(0)
    expect(page.get_by_test_id("computer-running")).to_be_visible()
    overlay = page.get_by_test_id("computer-overlay")
    overlay.get_by_role("button", name="Take control").click()
    expect(page.get_by_test_id("computer-label")).to_contain_text("You have control")
    expect(page.get_by_test_id("computer-label")).to_contain_text("idle 2 min")
    expect(page.get_by_test_id("computer-overlay-holder")).to_contain_text("You have control")
    expect(page.get_by_test_id("computer-overlay-holder")).to_contain_text("two idle minutes")
    expect(overlay.get_by_role("button", name="Release")).to_be_visible()
    overlay.get_by_role("button", name="Release").click()
    expect(page.get_by_test_id("computer-label")).not_to_contain_text("You have control")
    page.get_by_label("Close computer").click()
    expect(page.get_by_label("Close computer")).to_have_count(0)
    expect(page.get_by_test_id("computer-running")).to_be_visible()
    expect(page.get_by_test_id("computer-state")).to_have_attribute("data-state", "running")
    expect(page.get_by_text("Offline • Click to start")).to_have_count(0)


def test_settings_stop_shows_sleeping_on_pane(page: Page, client_url: str, host_url: str) -> None:
    name = unique_bot("Sleep")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name, private=True)
    open_computer_pane(page)
    page.get_by_test_id("computer-start").click()
    expect(page.get_by_test_id("computer-state")).to_have_attribute(
        "data-state", "running", timeout=15_000
    )
    expect(page.get_by_label("Close computer")).to_have_count(0)
    expect(page.get_by_test_id("computer-running")).to_be_visible()
    page.get_by_role("button", name="Settings").last.click()
    expect(page.get_by_test_id("computer-power-state")).to_contain_text("Running")
    page.get_by_test_id("computer-stop").click()
    expect(page.get_by_test_id("computer-power-state")).to_contain_text("Sleeping", timeout=8_000)
    page.get_by_label("Close settings").click()
    expect(page.get_by_test_id("computer-state")).to_have_attribute(
        "data-state", "sleeping", timeout=8_000
    )
    expect(page.get_by_text("Sleeping • Click to start")).to_be_visible()
    expect(page.get_by_text("Offline • Click to start")).to_have_count(0)
    page.get_by_test_id("computer-start").click()
    expect(page.get_by_test_id("computer-state")).to_have_attribute(
        "data-state", "running", timeout=15_000
    )
    expect(page.get_by_test_id("computer-overlay")).to_have_count(0)
    expect(page.get_by_test_id("computer-label")).not_to_contain_text("You have control")
    expect(page.get_by_role("button", name="Take control")).to_be_enabled()


def test_running_pane_embeds_novnc_without_clicking_start(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("View")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name, private=True)
    screen = (
        "/novnc/YWJj/6080/view/9999999999999."
        "abcdefghijklmnopqrstuvwxyz0123456789ABC/embed.html?view_only=true"
    )

    def computer_get(route):
        if route.request.method != "GET":
            route.continue_()
            return
        parts = route.request.url.split("?", 1)[0].rstrip("/").split("/")
        if parts[-1] == "screen":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"url": screen}),
            )
            return
        if len(parts) >= 2 and parts[-2] == "computer":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "bot_id": "bot_ui_preview",
                        "mode": "dedicated",
                        "kind": "docker",
                        "state": "running",
                        "control_holder": "none",
                        "screen_available": True,
                        "home_revision": None,
                        "busy_bot_name": None,
                    }
                ),
            )
            return
        route.continue_()

    page.route("**/v1/computer/**", computer_get)
    open_computer_pane(page)
    frame = page.locator("iframe[data-testid='computer-preview']")
    expect(frame).to_be_visible(timeout=8_000)
    expect(frame).to_have_attribute("src", re.compile(r"^/novnc/"))
    expect(page.get_by_test_id("computer-running")).to_have_count(0)
    expect(page.get_by_text("Preview · view only")).to_be_visible()
    expect(page.get_by_test_id("computer-state")).to_have_attribute("data-state", "running")
    expect(page.get_by_test_id("computer-label")).not_to_contain_text("You have control")


def test_release_keeps_view_preview_and_drops_control(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("RelView")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name, private=True)
    view = (
        "/novnc/YWJj/6080/view/9999999999999."
        "abcdefghijklmnopqrstuvwxyz0123456789ABC/embed.html?view_only=true"
    )
    control = (
        "/novnc/YWJj/6081/control/9999999999999."
        "abcdefghijklmnopqrstuvwxyz0123456789ABC/embed.html?view_only=false"
    )
    holder = {"value": "bot"}

    def computer_route(route):
        url = route.request.url.split("?", 1)[0]
        parts = url.rstrip("/").split("/")
        method = route.request.method
        if method == "POST" and parts[-1] == "takeover":
            holder["value"] = "user"
            route.continue_()
            return
        if method == "POST" and parts[-1] == "release":
            holder["value"] = "bot"
            route.continue_()
            return
        if method == "GET" and parts[-1] == "screen":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"url": control if holder["value"] == "user" else view}),
            )
            return
        route.continue_()

    page.route("**/v1/computer/**", computer_route)
    open_computer_pane(page)
    page.get_by_test_id("computer-start").click()
    expect(page.get_by_test_id("computer-state")).to_have_attribute(
        "data-state", "running", timeout=15_000
    )
    page.get_by_role("button", name="Take control").click()
    overlay = page.get_by_test_id("computer-overlay")
    expect(overlay).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("computer-overlay-holder")).to_contain_text("You have control")
    expect(overlay.locator("iframe")).to_have_attribute("src", re.compile(r"/control/"))
    overlay.get_by_role("button", name="Release").click()
    expect(page.get_by_test_id("computer-overlay-holder")).to_have_count(0)
    expect(overlay.get_by_role("button", name="Take control")).to_be_visible()
    expect(page.get_by_test_id("computer-label")).not_to_contain_text("You have control")
    expect(overlay.locator("iframe")).to_have_attribute("src", re.compile(r"/view/"))
    expect(overlay.locator("iframe")).to_have_attribute("src", re.compile(r"view_only=true"))


def test_bot_open_path_starts_computer_without_click(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("Wake")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name, private=True)
    open_computer_pane(page)
    expect(page.get_by_test_id("computer-state")).to_have_attribute("data-state", "offline")
    send_message(page, "e2e-wake-computer")
    card = page.get_by_test_id("consent-card")
    expect(card).to_be_visible(timeout=20_000)
    page.get_by_test_id("ask-option").filter(has_text="Always").click()
    expect(page.get_by_test_id("computer-state")).to_have_attribute(
        "data-state", "running", timeout=8_000
    )
    expect(page.get_by_test_id("computer-running")).to_be_visible()
    expect(page.get_by_text("The desktop is up.")).to_have_count(0)
    expect(page.get_by_text("Offline • Click to start")).to_have_count(0)


def test_chat_identity_city_shows_in_memory_pane(
    page: Page,
    client_url: str,
    host_url: str,
) -> None:
    name = unique_bot("Idn")
    stem = uuid.uuid4().hex[:8]
    first, second = f"Osijek{stem}", f"Split{stem}"
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    open_computer_pane(page)
    expect(page.get_by_test_id("new-memory")).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("memory-doc").filter(has_text=first)).to_have_count(0)

    send_message(page, f"please e2e-identity-city {first}")
    expect(page.get_by_test_id("thread").get_by_text("I'll remember that.")).to_be_visible(
        timeout=8_000
    )
    card = page.get_by_test_id("memory-doc").filter(has_text=first)
    expect(card).to_be_visible(timeout=8_000)
    expect(card).to_have_attribute("data-chapter", "identity")
    expect(card).to_contain_text("identity")

    send_message(page, f"please e2e-identity-city {second}")
    expect(page.get_by_test_id("memory-doc").filter(has_text=second)).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("memory-doc").filter(has_text=first)).to_have_count(0)


def test_hello_does_not_add_identity_city_card(
    page: Page,
    client_url: str,
    host_url: str,
) -> None:
    name = unique_bot("Idl")
    token = f"Cid{uuid.uuid4().hex[:8]}z"
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    send_message(page, "hello")
    expect(
        page.locator('[data-testid="thread-message"][data-role="bot"]').filter(has_text="ok")
    ).to_be_visible(timeout=8_000)
    open_computer_pane(page)
    expect(page.get_by_test_id("new-memory")).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("memory-doc").filter(has_text=token)).to_have_count(0)
