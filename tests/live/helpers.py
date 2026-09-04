from __future__ import annotations

import json
import subprocess
import threading
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlparse

from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
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
    overlay = page.get_by_label("Close computer")
    if overlay.count() > 0 and overlay.first.is_visible():
        overlay.first.click()
        expect(page.get_by_test_id("computer-overlay")).to_have_count(0)
    closer = page.get_by_title("Close panel")
    if closer.count() > 0 and closer.first.is_visible():
        closer.first.click()
        expect(page.get_by_test_id("new-memory")).to_have_count(0)


def arm_page(page: Page) -> None:
    page.set_default_timeout(8_000)
    page.set_default_navigation_timeout(20_000)


def open_computer_pane(page: Page) -> None:
    """Open the desktop-only computer context pane."""
    arm_page(page)
    state = page.get_by_test_id("computer-state")
    if state.count() > 0 and state.first.is_visible():
        return
    page.get_by_role("button", name="Computer").click()
    expect(state).to_be_visible(timeout=8_000)


def expect_cancelled_turn(page: Page) -> None:
    expect(page.get_by_test_id("run-error")).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("thread-stop")).to_have_count(0)
    expect(page.get_by_test_id("typing-indicator")).to_have_count(0)
    expect(composer(page)).to_be_enabled()


def expect_stays_absent(locator, timeout: int = 4_000) -> None:
    """Fail if the locator becomes visible while a cancelled late token could still land."""
    expect(locator).to_have_count(0)
    try:
        locator.first.wait_for(state="visible", timeout=timeout)
    except PlaywrightTimeoutError:
        expect(locator).to_have_count(0)
        return
    raise AssertionError("cancelled turn still appended after Stop")


def open_chat(page: Page, name: str) -> None:
    row = bot_row(page, name)
    if not row.is_visible(timeout=0):
        rail = page.get_by_test_id("workspace-rail")
        if rail.count() and rail.is_visible(timeout=0):
            rail.get_by_role("button", name="Chats").click()
    bot_row(page, name).click()
    expect(thread_header(page)).to_contain_text(name, timeout=8_000)


def open_models(page: Page) -> None:
    door = page.get_by_test_id("library-open-models")
    if not door.is_visible(timeout=0):
        rail = page.get_by_test_id("workspace-rail")
        if rail.count() and rail.is_visible(timeout=0):
            rail.get_by_role("button", name="Library").click()
    door = page.get_by_test_id("library-open-models")
    door.click()
    expect(page.get_by_test_id("models-pane")).to_be_visible(timeout=8_000)


def open_plugins(page: Page) -> None:
    door = page.get_by_test_id("library-open-plugins")
    if not door.is_visible(timeout=0):
        rail = page.get_by_test_id("workspace-rail")
        if rail.count() and rail.is_visible(timeout=0):
            rail.get_by_role("button", name="Library").click()
    page.get_by_test_id("library-open-plugins").click()
    expect(page.get_by_test_id("plugins-pane")).to_be_visible(timeout=8_000)


def _picker_values(page: Page, test_id: str) -> list[str]:
    picker = page.get_by_test_id(test_id)
    return picker.locator("[data-model]").evaluate_all(
        "els => els.map(el => el.getAttribute('data-model')).filter(Boolean)"
    )


def _close_models_ready(page: Page) -> None:
    page.get_by_role("button", name="Close Models").click()
    door = page.get_by_test_id("library-open-models")
    expect(door).to_have_attribute("data-models-ready", "true", timeout=8_000)


def ensure_model(page: Page) -> None:
    door = page.get_by_test_id("library-open-models")
    if not door.is_visible(timeout=0):
        rail = page.get_by_test_id("workspace-rail")
        if rail.count() and rail.is_visible(timeout=0):
            rail.get_by_role("button", name="Library").click()
    door = page.get_by_test_id("library-open-models")
    expect(door).to_be_visible(timeout=20_000)
    if door.get_attribute("data-models-ready") == "true":
        return
    open_models(page)
    cursor_status = page.get_by_test_id("models-status-cursor")
    if cursor_status.count() and cursor_status.first.is_visible(timeout=0):
        using = page.get_by_test_id("models-using")
        if using.count() and (using.inner_text() or "").strip():
            _close_models_ready(page)
            return
        retry = page.get_by_test_id("models-retry-cursor")
        if retry.count() and retry.first.is_visible(timeout=0) and retry.first.is_enabled():
            retry.click()
        picker = page.get_by_test_id("models-picker-cursor")
        expect(picker.locator("[data-model]").first).to_be_visible(timeout=20_000)
        values = _picker_values(page, "models-picker-cursor")
        if not values:
            raise AssertionError("Cursor model list was empty")
        chosen = "grok-4.6" if "grok-4.6" in values else values[0]
        using = page.get_by_test_id("models-using")
        if not using.count() or chosen not in (using.inner_text() or ""):
            picker.locator(f'[data-model="{chosen}"]').click()
            page.get_by_test_id("models-use-cursor").click()
        expect(page.get_by_test_id("models-using")).to_contain_text(chosen, timeout=8_000)
        _close_models_ready(page)
        return
    key = page.get_by_label("OpenRouter API key")
    if key.count() and key.first.is_visible(timeout=0):
        key.fill("test-secret-uiok")
        page.get_by_test_id("models-save-openrouter").click()
    expect(page.get_by_test_id("models-using")).to_be_visible(timeout=10_000)
    _close_models_ready(page)


def send_message(page: Page, text: str, bot_name: str | None = None) -> None:
    """Open this chat if named, type, press Enter, wait for the user bubble."""
    arm_page(page)
    ensure_model(page)
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
    page.get_by_test_id("workspace-rail").get_by_role("button", name="Library").click()
    expect(page.get_by_test_id("library-pane")).to_be_visible(timeout=8_000)
    page.get_by_test_id("library-open-settings").click()
    expect(page.get_by_text("Bot Settings")).to_be_visible(timeout=8_000)


def open_memory(page: Page, name: str) -> None:
    open_chat(page, name)
    page.get_by_test_id("workspace-rail").get_by_role("button", name="Library").click()
    expect(page.get_by_test_id("library-pane")).to_be_visible(timeout=8_000)
    page.get_by_test_id("library-open-memory").click()
    expect(page.get_by_role("heading", name="Memory")).to_be_visible(timeout=8_000)


def open_routines(page: Page, name: str) -> None:
    open_chat(page, name)
    page.get_by_test_id("workspace-rail").get_by_role("button", name="Routines").click()
    expect(page.get_by_role("heading", name="Routines")).to_be_visible(timeout=8_000)


def pair_fresh(page: Page, client_url: str, host_url: str, device_name: str | None = None) -> None:
    arm_page(page)
    page.goto(client_url, timeout=20_000, wait_until="domcontentloaded")
    form = page.get_by_test_id("pairing")
    expect(form).to_be_visible(timeout=20_000)
    form.get_by_text("Pairing options", exact=True).click()
    page.get_by_placeholder("https://host.example").fill(host_url)
    page.get_by_placeholder("XXXX-XXXX").fill(mint_pairing_code())
    if device_name is not None:
        page.get_by_label("Device name").fill(device_name)
    page.get_by_role("button", name="Pair").click()
    expect(page.get_by_test_id("today-view")).to_be_visible(timeout=20_000)
    page.get_by_test_id("workspace-rail").get_by_role("button", name="Chats").click()
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)


def fulfill_json(
    page: Page,
    url_glob: str,
    status: int,
    body: str = '{"detail":"test"}',
    *,
    method: str | None = None,
) -> None:
    def handle(route) -> None:
        if method and route.request.method != method:
            route.continue_()
            return
        route.fulfill(status=status, content_type="application/json", body=body)

    page.route(url_glob, handle)


def is_thread_snapshot_path(path: str) -> bool:
    parts = [item for item in path.split("/") if item]
    return len(parts) == 3 and parts[0] == "v1" and parts[1] == "threads"


@contextmanager
def hold_thread_snapshot_gets(page: Page) -> Iterator[threading.Event]:
    """Stall GET /v1/threads/{id} after the host has already produced the body."""
    held = threading.Event()
    release = threading.Event()

    def handle(route) -> None:
        request = route.request
        path = urlparse(request.url).path.rstrip("/")
        if request.method != "GET" or not is_thread_snapshot_path(path):
            route.continue_()
            return
        held.set()

        def resume() -> None:
            release.wait(timeout=30)
            try:
                route.continue_()
            except Exception:
                return

        threading.Thread(target=resume, daemon=True).start()

    page.route("**/v1/threads/**", handle)
    try:
        yield held
    finally:
        release.set()
        page.unroute("**/v1/threads/**", handle)


def cut_host(page: Page) -> None:
    """The throwaway host (or the path to it) is unreachable. Leave /local/* alone."""
    page.route("**/health", lambda route: route.abort())
    page.route("**/v1/**", lambda route: route.abort())


def restore_host(page: Page) -> None:
    """Drop every page.route, including a 404 fulfill on a specific path."""
    page.unroute_all()


def assert_readable_chip(chip) -> None:
    color = chip.evaluate("el => getComputedStyle(el).color")
    background = chip.evaluate("el => getComputedStyle(el).backgroundColor")
    ratio = _contrast_ratio(color, background)
    if ratio < 3.0:
        raise AssertionError(f"model chip contrast {ratio:.2f} < 3 ({color} on {background})")


def assert_readable_control(control) -> None:
    color = control.evaluate("el => getComputedStyle(el).color")
    background = control.evaluate("el => getComputedStyle(el).backgroundColor")
    ratio = _contrast_ratio(color, background)
    if ratio < 4.5:
        raise AssertionError(f"control contrast {ratio:.2f} < 4.5 ({color} on {background})")


def _css_rgb(value: str) -> tuple[int, int, int]:
    inner = value[value.find("(") + 1 : value.rfind(")")]
    parts = [float(item.strip()) for item in inner.split(",")[:3]]
    return int(parts[0]), int(parts[1]), int(parts[2])


def _rel_luminance(rgb: tuple[int, int, int]) -> float:
    def chan(raw: int) -> float:
        value = raw / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = rgb
    return 0.2126 * chan(red) + 0.7152 * chan(green) + 0.0722 * chan(blue)


def _contrast_ratio(color: str, background: str) -> float:
    first = _rel_luminance(_css_rgb(color))
    second = _rel_luminance(_css_rgb(background))
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def create_named_bot(
    page: Page,
    name: str,
    title: str | None = None,
    description: str | None = None,
    instructions: str | None = None,
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
        page.get_by_placeholder("e.g. Code Reviewer").fill(title)
    if description is not None:
        page.get_by_placeholder("What this bot is for").fill(description)
    if instructions is not None:
        page.get_by_placeholder("Standing orders for this bot").fill(instructions)
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
