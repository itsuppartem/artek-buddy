from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.live.helpers import create_named_bot, pair_fresh, send_message, unique_bot

pytestmark = pytest.mark.live

TINY = {"name": "n.txt", "mimeType": "text/plain", "buffer": b"n"}


def _named(page: Page, client_url: str, host_url: str, prefix: str) -> str:
    name = unique_bot(prefix)
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    return name


def test_owner_read_allow_once(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Read")
    send_message(page, "e2e-consent-read", name)
    card = page.get_by_test_id("consent-card")
    expect(card).to_be_visible(timeout=20_000)
    expect(card.get_by_test_id("ask-detail")).to_contain_text("owner_read")
    page.get_by_test_id("ask-option").filter(has_text="Allow once").click()
    expect(card).to_have_attribute("data-status", "answered", timeout=20_000)


def test_owner_write_and_list_allow(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Write")
    send_message(page, "e2e-consent-write", name)
    card = page.get_by_test_id("consent-card")
    expect(card).to_be_visible(timeout=20_000)
    page.get_by_test_id("ask-option").filter(has_text="Allow once").click()
    expect(card).to_have_attribute("data-status", "answered", timeout=20_000)
    send_message(page, "e2e-consent-list", name)
    listed = page.get_by_test_id("consent-card").last
    expect(listed).to_be_visible(timeout=20_000)
    listed.get_by_test_id("ask-option").filter(has_text="Allow once").click()
    expect(listed).to_have_attribute("data-status", "answered", timeout=20_000)


def test_owner_path_outside_home_is_denied(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Jail")
    send_message(page, "e2e-consent-read-escape", name)
    card = page.get_by_test_id("consent-card")
    expect(card).to_be_visible(timeout=20_000)
    page.get_by_test_id("ask-option").filter(has_text="Allow once").click()
    expect(card).to_contain_text("outside", timeout=8_000)


def test_auto_owner_read_has_no_card(page: Page, client_url: str, host_url: str) -> None:
    name = _named(page, client_url, host_url, "Auto")
    send_message(page, "e2e-consent-auto-read", name)
    expect(page.get_by_test_id("consent-card")).to_have_count(0)
    expect(page.locator('[data-testid="thread-message"][data-role="bot"]').last).to_contain_text(
        "got notes",
        timeout=20_000,
    )


def test_attach_over_file_count(page: Page, client_url: str, host_url: str) -> None:
    _named(page, client_url, host_url, "Files")
    files = [{**TINY, "name": f"f{i}.txt"} for i in range(11)]
    with page.expect_file_chooser() as chooser:
        page.get_by_role("button", name="Attach files").click()
    chooser.value.set_files(files)
    expect(page.get_by_test_id("action-error")).to_contain_text("At most 10 files", timeout=8_000)


def test_attach_over_file_size(page: Page, client_url: str, host_url: str) -> None:
    _named(page, client_url, host_url, "Huge")
    page.get_by_test_id("thread-composer").evaluate(
        """el => {
          const data = new DataTransfer();
          data.items.add(new File([new ArrayBuffer(25 * 1024 * 1024 + 1)], "huge.bin"));
          el.dispatchEvent(new DragEvent("drop", {bubbles: true, cancelable: true, dataTransfer: data}));
        }"""
    )
    expect(page.get_by_test_id("action-error")).to_contain_text("larger than 25 MB", timeout=8_000)


def test_attach_over_total_size(page: Page, client_url: str, host_url: str) -> None:
    _named(page, client_url, host_url, "Total")
    page.get_by_test_id("thread-composer").evaluate(
        """el => {
          const data = new DataTransfer();
          data.items.add(new File([new ArrayBuffer(24 * 1024 * 1024)], "a.bin"));
          data.items.add(new File([new ArrayBuffer(24 * 1024 * 1024)], "b.bin"));
          data.items.add(new File([new ArrayBuffer(4 * 1024 * 1024)], "c.bin"));
          el.dispatchEvent(new DragEvent("drop", {bubbles: true, cancelable: true, dataTransfer: data}));
        }"""
    )
    expect(page.get_by_test_id("action-error")).to_contain_text("too large together", timeout=8_000)
