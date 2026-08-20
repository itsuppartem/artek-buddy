from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import arm_page, fulfill_json, pair_fresh

pytestmark = pytest.mark.live


def test_proxy_error_retry_reloads_to_pairing(page: Page, client_url: str) -> None:
    arm_page(page)
    page.route("**/local/status", lambda route: route.abort())
    page.goto(client_url)
    card = page.get_by_test_id("proxy-error")
    expect(card).to_be_visible(timeout=20_000)
    page.unroute("**/local/status")
    card.get_by_role("button", name="Retry").click()
    expect(page.get_by_test_id("pairing")).to_be_visible(timeout=20_000)


def test_pairing_form_fields_and_rejected_url(page: Page, client_url: str) -> None:
    arm_page(page)
    page.goto(client_url)
    form = page.get_by_test_id("pairing")
    expect(form).to_be_visible(timeout=20_000)
    expect(page.get_by_label("Host URL")).to_be_visible()
    expect(page.get_by_label("Pairing code")).to_be_visible()
    expect(page.get_by_label("Device name")).to_have_value("This computer")
    expect(page.get_by_role("button", name="Pair")).to_be_disabled()

    page.get_by_placeholder("https://host.example").fill("https://evil.example")
    page.get_by_placeholder("XXXX-XXXX").fill("ABCD-EFGH")
    page.get_by_role("button", name="Pair").click()
    expect(page.get_by_test_id("pairing-error")).to_be_visible()


def test_pairing_with_device_name(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url, device_name="CI laptop")
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)


def test_auth_error_repair_returns_to_pairing(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    fulfill_json(page, "**/v1/**", 401, '{"detail":"invalid token"}')
    page.reload()
    card = page.get_by_test_id("auth-error")
    expect(card).to_be_visible(timeout=20_000)
    card.get_by_role("button", name="Pair this computer again").click()
    expect(page.get_by_test_id("pairing")).to_be_visible(timeout=20_000)


def test_host_error_retry_clears_banner(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    fulfill_json(page, "**/v1/**", 502, '{"detail":"upstream down"}')
    page.reload()
    card = page.get_by_test_id("host-error")
    expect(card).to_be_visible(timeout=20_000)
    page.unroute("**/v1/**")
    # The shell polls /health every 4s; once the route is off it may recover itself.
    if card.is_visible():
        card.get_by_role("button", name="Retry connection").click()
    expect(card).to_be_hidden(timeout=20_000)
    expect(page.get_by_test_id("thread-pane")).to_be_visible()


def test_action_error_dismiss_clears_banner(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    expect(page.get_by_test_id("thread-pane")).to_be_visible(timeout=20_000)
    fulfill_json(page, "**/v1/**", 400, '{"detail":"bad request"}')
    page.reload()
    card = page.get_by_test_id("action-error")
    expect(card).to_be_visible(timeout=20_000)
    card.get_by_role("button", name="Dismiss").click()
    expect(card).to_be_hidden()
