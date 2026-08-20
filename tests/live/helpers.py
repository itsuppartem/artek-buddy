from __future__ import annotations

import subprocess
import urllib.error
import urllib.request

from playwright.sync_api import Page, expect

from tests.support import mask_secret


def mint_pairing_code() -> str:
    raw = subprocess.check_output(
        ["docker", "exec", "artek-buddy", "python", "-m", "artek_buddy", "pair"],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    code = raw.strip().splitlines()[0].strip()
    mask_secret(code)
    return code


def reset_pairing(client_url: str) -> None:
    req = urllib.request.Request(
        client_url.rstrip("/") + "/local/unpair",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.URLError:
        return


def bot_row(page: Page, name: str):
    return page.locator(f'[data-testid="bot-row"][data-bot-name="{name}"]')


def composer(page: Page):
    return page.get_by_role("textbox", name="Message")


def send_message(page: Page, text: str) -> None:
    box = composer(page)
    box.wait_for()
    box.fill(text)
    page.get_by_role("button", name="Send").click()


def pair_fresh(page: Page, client_url: str, host_url: str, device_name: str | None = None) -> None:
    page.goto(client_url)
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


def _dismiss_boot_overlay(page: Page) -> None:
    overlay = page.get_by_text("Booting up", exact=False)
    if overlay.count():
        expect(overlay).to_have_count(0, timeout=20_000)
    closer = page.get_by_title("Close panel")
    if closer.count() and closer.first.is_visible():
        closer.click()


def create_named_bot(page: Page, name: str, title: str | None = None) -> None:
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    _dismiss_boot_overlay(page)
    search = page.get_by_placeholder("Search")
    if search.count():
        search.fill("")
    page.get_by_title("New bot").click()
    name_box = page.get_by_placeholder("Name this bot")
    expect(name_box).to_be_visible(timeout=10_000)
    name_box.fill(name)
    if title is not None:
        page.get_by_placeholder("Describe what this bot does").fill(title)
    page.get_by_role("button", name="Private").click()
    create = page.get_by_role("button", name="Create", exact=True)
    expect(create).to_be_enabled()
    create.click()
    row = bot_row(page, name)
    expect(row).to_have_count(1, timeout=20_000)
    row.scroll_into_view_if_needed()
    _dismiss_boot_overlay(page)
    composer(page).wait_for(timeout=20_000)


def open_bot_menu(page: Page, name: str) -> None:
    bot_row(page, name).click(button="right")
    expect(page.get_by_role("menu", name=f"Actions for {name}")).to_be_visible(timeout=10_000)


def ensure_bot(page: Page, name: str) -> None:
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    _dismiss_boot_overlay(page)
    empty = page.get_by_test_id("empty-bots")
    inbox = page.get_by_test_id("empty-inbox")
    rows = page.get_by_test_id("bot-row")
    expect(empty.or_(inbox).or_(rows.first)).to_be_visible(timeout=20_000)
    if rows.count() and rows.first.is_visible():
        composer(page).wait_for(timeout=20_000)
        return
    create_named_bot(page, name)
