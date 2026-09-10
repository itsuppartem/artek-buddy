from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    arm_page,
    bot_row,
    composer,
    expect_pairing_mark_inside_card,
    fulfill_json,
    thread_header,
    unique_bot,
)
from tests.live_web.helpers import (
    create_named_bot_phone,
    expect_bot_in_chats,
    open_phone_tab,
    pair_host_page,
    send_message_phone,
)

pytestmark = pytest.mark.live


def test_host_page_pairing_copy_has_no_token_or_module(page: Page, host_url: str) -> None:
    arm_page(page)
    page.goto(host_url, timeout=20_000, wait_until="domcontentloaded")
    form = page.get_by_test_id("pairing")
    expect(form).to_be_visible(timeout=20_000)
    expect(form.get_by_text("Pair this phone")).to_be_visible()
    expect_pairing_mark_inside_card(page)
    expect(form).to_contain_text(
        "Create a one-use pairing code on the host. Enter it here, then choose Pair."
    )
    expect(form).not_to_contain_text("token")
    expect(form).not_to_contain_text("mint")
    expect(form).not_to_contain_text("python -m")
    expect(page.get_by_test_id("pairing-host-command")).to_have_count(0)
    expect(page.get_by_placeholder("https://host.example")).to_have_count(0)
    expect(page.get_by_role("button", name="Pair")).to_be_disabled()


def test_host_page_pairs_and_stacks_on_iphone_11_pro(page: Page, host_url: str) -> None:
    box = page.viewport_size
    assert box == {"width": 375, "height": 812}
    pair_host_page(page, host_url)
    expect(page.get_by_test_id("phone-desk-pad")).to_have_count(0)
    name = unique_bot("PhoneWin")
    create_named_bot_phone(page, name)
    expect(page.get_by_test_id("thread-header")).to_contain_text(name, timeout=8_000)
    expect_bot_in_chats(page, name)
    open_phone_tab(page, "desk")
    expect(page.get_by_test_id("computer-state")).to_be_visible(timeout=8_000)
    expect(page.get_by_text("Settings", exact=True)).to_have_count(0)
    expect(page.get_by_test_id("new-memory")).to_have_count(0)
    page.get_by_title("Close panel").click()
    expect(page.get_by_test_id("phone-tab-chats")).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("thread-header")).to_contain_text(name)


def test_host_page_home_screen_hint_leaves_models_tappable(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    expect(page.get_by_test_id("home-screen-hint")).to_be_visible()
    open_phone_tab(page, "more")
    expect(page.get_by_test_id("home-screen-hint")).to_be_visible()
    page.get_by_test_id("library-open-models").click()
    expect(page.get_by_test_id("models-pane")).to_be_visible(timeout=8_000)


def test_phone_appearance_follows_system_and_allows_override(page: Page, host_url: str) -> None:
    page.emulate_media(color_scheme="dark")
    pair_host_page(page, host_url)
    create_named_bot_phone(page, unique_bot("PhoneTheme"))
    open_phone_tab(page, "more")

    picker = page.get_by_test_id("theme-picker")
    expect(picker.get_by_role("radio", name="System")).to_be_checked()
    expect(page.locator("body")).to_have_css("background-color", "rgb(13, 23, 39)")

    picker.get_by_text("Light", exact=True).click()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    expect(page.locator("body")).to_have_css("background-color", "rgb(244, 247, 251)")
    expect(page.get_by_test_id("phone-tab-more")).to_have_attribute("aria-current", "page")


def test_phone_computer_open_close_returns_to_chat(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    name = unique_bot("DeskBack")
    create_named_bot_phone(page, name)
    expect(page.get_by_test_id("phone-tab-chats")).to_have_attribute("aria-current", "page")
    page.get_by_role("button", name="Computer").click()
    expect(page.get_by_test_id("phone-tab-desk")).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("computer-state")).to_be_visible(timeout=8_000)
    page.get_by_title("Close panel").click()
    expect(page.get_by_test_id("phone-tab-chats")).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("thread-header")).to_contain_text(name)
    expect(page.get_by_test_id("thread-pane")).to_be_visible()
    expect(page.get_by_test_id("computer-state")).to_have_count(0)


def test_phone_models_plugins_close_returns_to_more(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    name = unique_bot("HatchBack")
    create_named_bot_phone(page, name)
    open_phone_tab(page, "more")
    page.get_by_test_id("library-open-models").click()
    expect(page.get_by_test_id("models-pane")).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("phone-tab-more")).to_have_attribute("aria-current", "page")
    page.get_by_role("button", name="Close Models").click()
    expect(page.get_by_test_id("phone-tab-more")).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("library-pane")).to_be_visible()
    expect(page.get_by_test_id("models-pane")).to_have_count(0)

    page.get_by_test_id("library-open-plugins").click()
    expect(page.get_by_test_id("plugins-pane")).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("phone-tab-more")).to_have_attribute("aria-current", "page")
    page.get_by_role("button", name="Close Plugins").click()
    expect(page.get_by_test_id("phone-tab-more")).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("library-pane")).to_be_visible()
    expect(page.get_by_test_id("plugins-pane")).to_have_count(0)


def test_host_page_auth_error_says_pair_this_phone_again(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    expect(page.get_by_test_id("today-view")).to_be_visible(timeout=20_000)
    fulfill_json(page, "**/v1/**", 401, '{"detail":"invalid token"}')
    page.reload()
    card = page.get_by_test_id("auth-error")
    expect(card).to_be_visible(timeout=20_000)
    expect(card.get_by_role("button", name="Pair this computer again")).to_have_count(0)
    card.get_by_role("button", name="Pair this phone again").click()
    expect(page.get_by_test_id("pairing")).to_be_visible(timeout=20_000)
    expect(page.get_by_text("Pair this phone")).to_be_visible()
    expect(page.get_by_placeholder("https://host.example")).to_have_count(0)


def test_host_page_workspace_events_auth_says_pair_this_phone_again(
    page: Page, host_url: str
) -> None:
    pair_host_page(page, host_url)
    open_phone_tab(page, "today")
    expect(page.get_by_test_id("today-view")).to_be_visible(timeout=20_000)
    fulfill_json(page, "**/v1/events", 401, '{"detail":"invalid token"}')
    page.reload()
    expect(page.get_by_test_id("phone-nav")).to_be_visible(timeout=20_000)
    expect(page.get_by_test_id("auth-error")).to_be_visible(timeout=20_000)
    # Leftover host bots can put a helper id in the hash; reload then opens that
    # chat. Auth loss still has to show on the paired shell, not kick to pairing.
    if page.get_by_test_id("phone-tab-today").get_attribute("aria-current") != "page":
        open_phone_tab(page, "today")
    expect(page.get_by_test_id("today-view")).to_be_visible(timeout=20_000)
    expect(page.get_by_role("button", name="Pair this computer again")).to_have_count(0)
    expect(page.get_by_test_id("pairing")).to_have_count(0)
    page.get_by_role("button", name="Pair this phone again").click()
    expect(page.get_by_test_id("pairing")).to_be_visible(timeout=20_000)
    expect(page.get_by_text("Pair this phone")).to_be_visible()


def test_host_page_unsent_draft_stays_on_the_chat_it_was_typed_in(
    page: Page, host_url: str
) -> None:
    first = unique_bot("DraftWebA")
    second = unique_bot("DraftWebB")
    pair_host_page(page, host_url)
    create_named_bot_phone(page, first)
    create_named_bot_phone(page, second)
    open_phone_tab(page, "chats")
    bot_row(page, first).click()
    expect(thread_header(page)).to_contain_text(first, timeout=8_000)
    open_phone_tab(page, "chat")
    box = composer(page)
    box.fill("keep on A")
    expect(box).to_have_value("keep on A")
    open_phone_tab(page, "chats")
    bot_row(page, second).click()
    expect(thread_header(page)).to_contain_text(second, timeout=8_000)
    open_phone_tab(page, "chat")
    expect(composer(page)).to_have_value("")
    open_phone_tab(page, "chats")
    bot_row(page, first).click()
    expect(thread_header(page)).to_contain_text(first, timeout=8_000)
    open_phone_tab(page, "chat")
    expect(composer(page)).to_have_value("keep on A")


def test_host_page_got_it_dismisses_home_screen_hint(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    hint = page.get_by_test_id("home-screen-hint")
    expect(hint).to_be_visible()
    page.get_by_role("button", name="Got it").click()
    expect(page.get_by_test_id("home-screen-hint")).to_have_count(0)
    page.reload()
    expect(page.get_by_test_id("home-screen-hint")).to_have_count(0)


def test_host_page_turn_on_alerts_offered_in_standalone_app(page: Page, host_url: str) -> None:
    page.add_init_script(
        """
        Object.defineProperty(navigator, 'standalone', { value: true, configurable: true });
        window.__mockNotificationPermission = 'default';
        window.Notification = {
            get permission() { return window.__mockNotificationPermission; },
            requestPermission: () => {
                window.__mockNotificationPermission = 'granted';
                return Promise.resolve('granted');
            }
        };
        """
    )
    pair_host_page(page, host_url, expect_hint=False)
    expect(page.get_by_test_id("home-screen-hint")).to_have_count(0)
    alerts_btn = page.get_by_test_id("turn-on-alerts")
    expect(alerts_btn).to_be_visible()
    expect(alerts_btn).to_contain_text("Turn on alerts — only while this app is open")
    alerts_btn.click()
    expect(page.get_by_test_id("turn-on-alerts")).to_have_count(0)


def test_host_page_turn_on_alerts_denied_hides_offer(page: Page, host_url: str) -> None:
    page.add_init_script(
        """
        Object.defineProperty(navigator, 'standalone', { value: true, configurable: true });
        window.__mockNotificationPermission = 'default';
        window.Notification = {
            get permission() { return window.__mockNotificationPermission; },
            requestPermission: () => {
                window.__mockNotificationPermission = 'denied';
                return Promise.resolve('denied');
            }
        };
        """
    )
    pair_host_page(page, host_url, expect_hint=False)
    alerts_btn = page.get_by_test_id("turn-on-alerts")
    expect(alerts_btn).to_be_visible()
    alerts_btn.click()
    expect(page.get_by_test_id("turn-on-alerts")).to_have_count(0)


def test_host_page_stacked_shell_at_812x375_landscape(page: Page, host_url: str) -> None:
    page.set_viewport_size({"width": 812, "height": 375})
    pair_host_page(page, host_url)
    expect(page.get_by_test_id("phone-nav")).to_be_visible()
    today_tab = page.get_by_test_id("phone-tab-today")
    chats_tab = page.get_by_test_id("phone-tab-chats")
    desk_tab = page.get_by_test_id("phone-tab-desk")
    more_tab = page.get_by_test_id("phone-tab-more")
    expect(today_tab).to_be_visible()
    expect(chats_tab).to_be_visible()
    expect(desk_tab).to_be_visible()
    expect(more_tab).to_be_visible()
    expect(today_tab).to_have_attribute("aria-current", "page")

    name = unique_bot("LandBot")
    create_named_bot_phone(page, name)
    expect(page.get_by_test_id("thread-header")).to_contain_text(name, timeout=8_000)
    expect(chats_tab).to_have_attribute("aria-current", "page")

    open_phone_tab(page, "more")
    expect(page.get_by_test_id("library-pane")).to_be_visible(timeout=8_000)
    expect(more_tab).to_have_attribute("aria-current", "page")


def test_host_page_pairing_invalid_code_shows_error(page: Page, host_url: str) -> None:
    arm_page(page)
    page.goto(host_url, timeout=20_000, wait_until="domcontentloaded")
    form = page.get_by_test_id("pairing")
    expect(form).to_be_visible(timeout=20_000)
    page.get_by_placeholder("XXXX-XXXX").fill("0000-0000")
    pair_btn = page.get_by_role("button", name="Pair")
    expect(pair_btn).to_be_enabled()
    pair_btn.click()
    error = page.get_by_test_id("pairing-error")
    expect(error).to_be_visible(timeout=10_000)
    expect(page.get_by_test_id("phone-nav")).to_have_count(0)


def test_phone_create_cancel_returns_to_previous_context(page: Page, host_url: str) -> None:
    pair_host_page(page, host_url)
    open_phone_tab(page, "chats")
    page.get_by_role("button", name="New bot").click()
    expect(page.get_by_placeholder("Name this bot")).to_be_visible(timeout=8_000)
    page.get_by_test_id("create-cancel").click()
    expect(page.get_by_placeholder("Name this bot")).to_have_count(0)
    expect(page.get_by_test_id("phone-tab-chats")).to_have_attribute("aria-current", "page")

    name = unique_bot("CancelBot")
    create_named_bot_phone(page, name)
    expect(page.get_by_test_id("thread-header")).to_contain_text(name, timeout=8_000)
    open_phone_tab(page, "chats")
    page.get_by_role("button", name="New bot").click()
    expect(page.get_by_placeholder("Name this bot")).to_be_visible(timeout=8_000)
    page.get_by_test_id("create-cancel").click()
    expect(page.get_by_placeholder("Name this bot")).to_have_count(0)
    open_phone_tab(page, "chat")
    expect(page.get_by_test_id("thread-header")).to_contain_text(name)


def test_host_page_today_does_not_mark_hidden_thread_read(page: Page, host_url: str) -> None:
    name = unique_bot("HideRead")
    pair_host_page(page, host_url)
    create_named_bot_phone(page, name)
    send_message_phone(page, "please e2e-slow")
    open_phone_tab(page, "today")
    today = page.get_by_test_id("today-view")
    expect(today).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("thread-pane")).to_be_hidden()
    expect(today).to_contain_text("slow done", timeout=15_000)
    open_phone_tab(page, "chats")
    expect(bot_row(page, name).get_by_test_id("unread-dot")).to_be_visible(timeout=8_000)
