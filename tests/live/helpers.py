from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
import uuid

from playwright.sync_api import Page, expect
from tests.support import mask_secret


def mint_pairing_code() -> str:
    raw = subprocess.check_output(
        ["docker", "exec", "artek-buddy", "python", "-m", "artek_buddy", "pair"],
        text=True,
        stderr=subprocess.DEVNULL,
        timeout=15,
    )
    code = raw.strip().splitlines()[0].strip()
    mask_secret(code)
    return code


def reset_pairing(client_url: str) -> None:
    origin = client_url.rstrip("/")
    try:
        status_req = urllib.request.Request(
            origin + "/local/status",
            method="GET",
            headers={"Origin": origin, "Accept": "application/json"},
        )
        with urllib.request.urlopen(status_req, timeout=5) as resp:
            payload = json.loads(resp.read().decode())
        nonce = str(payload.get("nonce") or "")
        req = urllib.request.Request(
            origin + "/local/unpair",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Artek-Local-Nonce": nonce,
            },
        )
        urllib.request.urlopen(req, timeout=5)
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
        return


def unique_bot(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


def bot_row(page: Page, name: str):
    return page.locator(f'[data-testid="bot-row"][data-bot-name="{name}"]')


def composer(page: Page):
    return page.get_by_role("textbox", name="Message")


def thread_header(page: Page):
    return page.get_by_test_id("thread-header")


def close_computer_pane(page: Page) -> None:
    closer = page.get_by_title("Close panel")
    try:
        if closer.count() and closer.first.is_visible(timeout=0):
            closer.first.click(timeout=2_000)
    except Exception:
        pass
    overlay = page.get_by_label("Close computer")
    try:
        if overlay.count() and overlay.first.is_visible(timeout=0):
            overlay.first.click(timeout=2_000)
    except Exception:
        pass


def arm_page(page: Page) -> None:
    page.set_default_timeout(8_000)
    page.set_default_navigation_timeout(20_000)


def open_computer_pane(page: Page) -> None:
    """Memory and routines live in the side pane. Gear does not boot the desktop."""
    arm_page(page)
    closer = page.get_by_title("Close panel")
    memory = page.get_by_test_id("new-memory")
    try:
        if closer.count() and closer.first.is_visible(timeout=0):
            expect(memory).to_be_visible(timeout=8_000)
            return
    except Exception:
        pass
    try:
        if memory.count() and memory.first.is_visible(timeout=0):
            return
    except Exception:
        pass
    page.get_by_role("button", name="Computer").click(timeout=5_000)
    expect(memory).to_be_visible(timeout=8_000)


def open_chat(page: Page, name: str) -> None:
    bot_row(page, name).click()
    expect(thread_header(page)).to_contain_text(name, timeout=8_000)


def send_message(page: Page, text: str, bot_name: str | None = None) -> None:
    """Open this chat if named, type, press Enter, wait for the user bubble."""
    arm_page(page)
    if bot_name:
        open_chat(page, bot_name)
    box = composer(page)
    expect(box).to_be_enabled(timeout=8_000)
    box.fill(text)
    expect(box).to_have_value(text)
    box.press("Enter")
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(has_text=text)
    ).to_be_visible(timeout=8_000)


def open_settings(page: Page, name: str) -> None:
    open_chat(page, name)
    page.get_by_role("button", name="Settings").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible(timeout=8_000)


def pair_fresh(page: Page, client_url: str, host_url: str, device_name: str | None = None) -> None:
    arm_page(page)
    page.goto(client_url, timeout=20_000, wait_until="domcontentloaded")
    form = page.get_by_test_id("pairing")
    expect(form).to_be_visible(timeout=20_000)
    page.get_by_placeholder("https://host.example").fill(host_url)
    page.get_by_placeholder("XXXX-XXXX").fill(mint_pairing_code())
    if device_name is not None:
        page.get_by_label("Device name").fill(device_name)
    page.get_by_role("button", name="Pair").click()
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)


def fulfill_json(page: Page, url_glob: str, status: int, body: str = '{"detail":"test"}') -> None:
    page.route(
        url_glob,
        lambda route: route.fulfill(status=status, content_type="application/json", body=body),
    )


def create_named_bot(
    page: Page,
    name: str,
    title: str | None = None,
    description: str | None = None,
    *,
    private: bool | None = None,
) -> None:
    """New bot is always in the sidebar. Product default is Team; pass private=True for a dedicated desktop."""
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    page.get_by_role("button", name="New bot").click()
    box = page.get_by_placeholder("Name this bot")
    expect(box).to_be_visible(timeout=10_000)
    box.fill(name)
    if title is not None:
        page.get_by_placeholder("Describe what this bot does").fill(title)
    if description is not None:
        page.get_by_placeholder("What this bot is for").fill(description)
    if private is True:
        page.get_by_test_id("computer-mode-private").click()
    elif private is False:
        page.get_by_test_id("computer-mode-team").click()
    page.get_by_role("button", name="Create", exact=True).click()
    expect(page.get_by_placeholder("Name this bot")).to_have_count(0, timeout=20_000)
    expect(bot_row(page, name)).to_have_count(1, timeout=20_000)
    open_chat(page, name)
    composer(page).wait_for(timeout=20_000)


def open_bot_menu(page: Page, name: str) -> None:
    bot_row(page, name).click(button="right")
    expect(page.get_by_role("menu", name=f"Actions for {name}")).to_be_visible(timeout=10_000)


def ensure_bot(page: Page, name: str, *, private: bool | None = None) -> None:
    """Open this named chat, or create it."""
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    row = bot_row(page, name)
    if row.count() and row.first.is_visible(timeout=0):
        open_chat(page, name)
        composer(page).wait_for(timeout=20_000)
        return
    create_named_bot(page, name, private=private)
