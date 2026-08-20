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


def close_computer_pane(page: Page) -> None:
    """Create opens the computer pane; the noVNC iframe 502-loops and CDP sits."""
    for loc in (
        page.get_by_title("Close panel"),
        page.get_by_label("Close computer"),
    ):
        try:
            if loc.count() and loc.first.is_visible(timeout=0):
                loc.first.click(timeout=2_000)
        except Exception:
            pass


def arm_page(page: Page) -> None:
    page.set_default_timeout(8_000)
    page.set_default_navigation_timeout(20_000)


def open_computer_pane(page: Page) -> None:
    """Memory and routines live in the side pane. Do not toggle an already-open pane shut."""
    arm_page(page)
    closer = page.get_by_title("Close panel")
    memory = page.get_by_test_id("new-memory")
    try:
        if closer.count() and closer.first.is_visible(timeout=0):
            expect(memory).to_be_visible(timeout=20_000)
            return
    except Exception:
        pass
    try:
        if memory.count() and memory.first.is_visible(timeout=0):
            return
    except Exception:
        pass
    page.get_by_title("Agent computer").click(timeout=5_000)
    expect(memory).to_be_visible(timeout=20_000)


def fill_react_input(locator, text: str) -> None:
    """Playwright fill() can set the DOM without React draft, then a rerender wipes it."""
    locator.wait_for(timeout=8_000)
    locator.evaluate(
        """(el, value) => {
          const proto = el.tagName === "TEXTAREA"
            ? window.HTMLTextAreaElement.prototype
            : window.HTMLInputElement.prototype;
          const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
          setter.call(el, value);
          el.dispatchEvent(new Event("input", { bubbles: true }));
        }""",
        text,
    )


def send_message(page: Page, text: str) -> None:
    """Type into the composer and press Enter. Do not click Send: the attention
    pill covers it, and clicking the pill opens a leftover bot instead.
    """
    arm_page(page)
    close_computer_pane(page)
    booting = page.get_by_text("Booting up")
    try:
        if booting.count():
            booting.first.wait_for(state="hidden", timeout=8_000)
    except Exception:
        pass
    box = composer(page)
    box.click(timeout=8_000)
    fill_react_input(box, text)
    box.press("Enter")
    expect(
        page.locator('[data-testid="thread-message"][data-role="user"]').filter(has_text=text)
    ).to_be_visible(timeout=8_000)


def open_settings(page: Page, name: str) -> None:
    page.locator('[data-testid="thread-pane"] button').filter(has_text=name).click(timeout=5_000)
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
    close_computer_pane(page)


def fulfill_json(page: Page, url_glob: str, status: int, body: str = '{"detail":"test"}') -> None:
    page.route(
        url_glob,
        lambda route: route.fulfill(status=status, content_type="application/json", body=body),
    )


def create_named_bot(
    page: Page,
    name: str,
    title: str | None = None,
    *,
    close_pane: bool = True,
    private: bool = True,
) -> None:
    """+ is always in the sidebar. Private so Create does not paint Team Booting up.
    Create opens the computer pane (memory / routines live there). Thread tests
    close it so noVNC cannot sit on later clicks; the memory test keeps it open.
    """
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    page.get_by_title("New bot").click()
    box = page.get_by_placeholder("Name this bot")
    expect(box).to_be_visible(timeout=10_000)
    box.fill(name)
    if title is not None:
        page.get_by_placeholder("Describe what this bot does").fill(title)
    if private:
        page.get_by_role("button", name="Private").click()
    page.get_by_role("button", name="Create", exact=True).click()
    expect(bot_row(page, name)).to_have_count(1, timeout=20_000)
    if close_pane:
        close_computer_pane(page)
    bot_row(page, name).click()
    expect(page.locator('[data-testid="thread-pane"] button').filter(has_text=name)).to_be_visible(
        timeout=8_000
    )
    composer(page).wait_for(timeout=20_000)
    if close_pane:
        close_computer_pane(page)


def open_bot_menu(page: Page, name: str) -> None:
    bot_row(page, name).click(button="right")
    expect(page.get_by_role("menu", name=f"Actions for {name}")).to_be_visible(timeout=10_000)


def ensure_bot(page: Page, name: str) -> None:
    """Open this named chat. Leftover host bots must not steal Send."""
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    row = bot_row(page, name)
    if row.count() and row.first.is_visible(timeout=0):
        row.click()
        expect(page.locator('[data-testid="thread-pane"] button').filter(has_text=name)).to_be_visible(
            timeout=8_000
        )
        composer(page).wait_for(timeout=20_000)
        return
    create_named_bot(page, name)
