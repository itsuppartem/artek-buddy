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
        timeout=15,
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


def dismiss_attention(page: Page) -> None:
    """The attention pill sits on top of Send/Stop. Playwright then waits 30s."""
    banner = page.get_by_test_id("attention-alert")
    try:
        if banner.count() and banner.is_visible():
            banner.click(timeout=1_000)
    except Exception:
        return


def close_computer_pane(page: Page) -> None:
    """Create opens the computer pane; the noVNC iframe 502-loops and CDP sits."""
    for loc in (
        page.get_by_title("Close panel"),
        page.get_by_label("Close computer"),
    ):
        try:
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=2_000)
        except Exception:
            pass


def _fail_fast_clicks(page: Page) -> None:
    page.set_default_timeout(8_000)
    page.set_default_navigation_timeout(20_000)


def send_message(page: Page, text: str) -> None:
    _fail_fast_clicks(page)
    dismiss_attention(page)
    box = composer(page)
    box.wait_for()
    box.fill(text)
    page.get_by_role("button", name="Send").click(timeout=5_000, force=True)


def open_settings(page: Page, name: str) -> None:
    page.locator('[data-testid="thread-pane"] button').filter(has_text=name).click()
    expect(page.get_by_text("Bot Settings")).to_be_visible(timeout=10_000)


def pair_fresh(page: Page, client_url: str, host_url: str, device_name: str | None = None) -> None:
    _fail_fast_clicks(page)
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


def create_named_bot(page: Page, name: str, title: str | None = None) -> None:
    """+ is always in the sidebar. Private so Create does not boot Team.
    Close the computer pane and the attention banner so later clicks are free."""
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    page.get_by_title("New bot").click()
    box = page.get_by_placeholder("Name this bot")
    expect(box).to_be_visible(timeout=10_000)
    box.fill(name)
    if title is not None:
        page.get_by_placeholder("Describe what this bot does").fill(title)
    page.get_by_role("button", name="Private").click()
    page.get_by_role("button", name="Create", exact=True).click()
    expect(bot_row(page, name)).to_have_count(1, timeout=20_000)
    composer(page).wait_for(timeout=20_000)
    close_computer_pane(page)
    dismiss_attention(page)


def open_bot_menu(page: Page, name: str) -> None:
    bot_row(page, name).click(button="right")
    expect(page.get_by_role("menu", name=f"Actions for {name}")).to_be_visible(timeout=10_000)


def ensure_bot(page: Page, name: str) -> None:
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    empty = page.get_by_test_id("empty-bots")
    inbox = page.get_by_test_id("empty-inbox")
    rows = page.get_by_test_id("bot-row")
    expect(empty.or_(inbox).or_(rows.first)).to_be_visible(timeout=20_000)
    if rows.count() and rows.first.is_visible():
        composer(page).wait_for(timeout=20_000)
        return
    create_named_bot(page, name)
