from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    assert_readable_chip,
    composer,
    create_named_bot,
    ensure_model,
    fulfill_json,
    open_models,
    pair_fresh,
    restore_host,
    send_message,
    unique_bot,
)

from artek_buddy.model_catalog import NEEDS_MODEL_TEXT

pytestmark = pytest.mark.live


def test_models_empty_save_pick_send_and_forget(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, unique_bot("Keys"))
    open_models(page)
    for provider in ("cursor", "openrouter", "openai", "anthropic", "xai"):
        forget = page.get_by_test_id(f"models-forget-{provider}")
        if forget.count() and forget.first.is_visible(timeout=0):
            forget.click()
    page.get_by_role("button", name="Close Models").click()
    expect(page.get_by_test_id("needs-model")).to_contain_text("Open Models")
    open_models(page)
    for name in ("Cursor", "OpenRouter", "OpenAI", "Anthropic", "xAI (Grok)"):
        expect(page.get_by_test_id("models-pane").get_by_text(name, exact=True)).to_be_visible()
    expect(page.get_by_test_id("models-default")).to_have_count(0)
    expect(page.get_by_test_id("models-forget-openrouter")).to_have_count(0)
    expect(
        page.get_by_test_id("models-picker-openrouter").get_by_text("No models yet")
    ).to_be_visible(timeout=8_000)
    save_cursor = page.get_by_test_id("models-save-cursor")
    expect(save_cursor).to_be_enabled()
    save_cursor.click()
    expect(page.get_by_test_id("models-error-cursor")).to_contain_text("Paste a key first")
    page.get_by_label("Cursor API key").fill("crsr_test-save-fail")
    expect(page.get_by_label("Cursor API key")).to_have_value("crsr_test-save-fail")
    fulfill_json(page, "**/v1/models/credentials", 404, '{"detail":"Not Found"}', method="POST")
    save_cursor.click()
    expect(page.get_by_test_id("models-error-cursor")).to_contain_text("Not Found")
    restore_host(page)
    page.get_by_role("button", name="Close Models").click()

    box = composer(page)
    box.fill("hello without a key")
    expect(box).to_have_value("hello without a key")
    page.get_by_role("button", name="Send").click()
    expect(page.get_by_test_id("thread-message").filter(has_text=NEEDS_MODEL_TEXT)).to_be_visible(
        timeout=8_000
    )

    ensure_model(page)
    expect(page.get_by_test_id("needs-model")).to_have_count(0)

    open_models(page)
    expect(page.get_by_test_id("models-status-openrouter")).to_contain_text("•••• uiok")
    expect(page.get_by_test_id("models-status-openrouter")).to_contain_text("Connected")
    expect(page.get_by_label("OpenRouter API key")).to_have_count(0)
    expect(page.get_by_test_id("models-picker-openrouter").locator("select")).to_have_count(0)
    chip = page.get_by_test_id("models-picker-openrouter").locator("[data-model]").first
    expect(chip).to_be_visible()
    assert_readable_chip(chip)
    expect(page.get_by_test_id("models-using")).to_contain_text("scripted")
    page.get_by_test_id("models-forget-openrouter").click()
    expect(page.get_by_label("OpenRouter API key")).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("models-forget-openrouter")).to_have_count(0)
    page.get_by_role("button", name="Close Models").click()
    expect(page.get_by_test_id("needs-model")).to_be_visible(timeout=8_000)


def test_models_cursor_save_sets_effort_fast_and_keeps_using(
    page: Page, client_url: str, host_url: str
) -> None:
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, unique_bot("CursorKey"))
    open_models(page)
    leftover = page.get_by_test_id("models-forget-cursor")
    if leftover.count() and leftover.first.is_visible(timeout=0):
        leftover.click()
        expect(page.get_by_label("Cursor API key")).to_be_visible()
    page.get_by_label("Cursor API key").fill("test-secret-cursor")
    expect(page.get_by_label("Cursor API key")).to_have_value("test-secret-cursor")
    page.get_by_test_id("models-save-cursor").click()
    expect(page.get_by_test_id("models-status-cursor")).to_contain_text("Connected", timeout=8_000)
    expect(page.get_by_test_id("models-using")).to_contain_text("scripted")
    expect(page.get_by_test_id("models-effort-cursor")).to_have_value("xhigh")
    expect(page.get_by_test_id("models-fast-cursor")).to_be_checked()
    chip = page.get_by_test_id("models-picker-cursor").locator("[data-model]").first
    expect(chip).to_be_visible()
    assert_readable_chip(chip)
    page.get_by_role("button", name="Close Models").click()
    open_models(page)
    expect(page.get_by_test_id("models-using")).to_contain_text("scripted")
    expect(page.get_by_test_id("models-effort-cursor")).to_have_value("xhigh")
    expect(page.get_by_test_id("models-fast-cursor")).to_be_checked()
    page.get_by_test_id("models-forget-cursor").click()
    expect(page.get_by_label("Cursor API key")).to_be_visible(timeout=8_000)


def test_models_save_reasoning_writes_meta_and_keeps_a_live_turn(
    page: Page, client_url: str, host_url: str
) -> None:
    name = unique_bot("Reason")
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, name)
    open_models(page)
    leftover = page.get_by_test_id("models-forget-cursor")
    if leftover.count() and leftover.first.is_visible(timeout=0):
        leftover.click()
        expect(page.get_by_label("Cursor API key")).to_be_visible()
    page.get_by_label("Cursor API key").fill("test-secret-cursor")
    expect(page.get_by_label("Cursor API key")).to_have_value("test-secret-cursor")
    page.get_by_test_id("models-save-cursor").click()
    expect(page.get_by_test_id("models-status-cursor")).to_contain_text("Connected", timeout=8_000)
    expect(page.get_by_test_id("models-using")).to_contain_text("scripted")
    expect(page.get_by_test_id("models-use-cursor")).to_be_enabled()
    expect(page.get_by_test_id("models-save-settings-cursor")).to_have_count(0)
    page.get_by_test_id("models-effort-cursor").select_option("low")
    expect(page.get_by_test_id("models-using")).to_contain_text("Low", timeout=8_000)
    page.get_by_role("button", name="Close Models").click()
    expect(page.get_by_test_id("meta-block")).to_contain_text("Using scripted · Low", timeout=8_000)
    open_models(page)
    expect(page.get_by_test_id("models-effort-cursor")).to_have_value("low")
    page.get_by_role("button", name="Close Models").click()
    send_message(page, "please e2e-hang now", name)
    expect(page.get_by_test_id("thread-stop")).to_be_visible(timeout=8_000)
    open_models(page)
    page.get_by_test_id("models-effort-cursor").select_option("high")
    expect(page.get_by_test_id("models-using")).to_contain_text("High", timeout=8_000)
    page.get_by_role("button", name="Close Models").click()
    expect(
        page.get_by_test_id("meta-block").filter(has_text="This turn keeps going.")
    ).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("run-error")).to_have_count(0)
    expect(page.get_by_test_id("thread-stop")).to_be_visible()


def test_models_one_commit_and_empty_provider_next_step(
    page: Page, client_url: str, host_url: str
) -> None:
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, unique_bot("OneCommit"))
    open_models(page)
    for provider in ("cursor", "openrouter", "openai", "anthropic", "xai"):
        forget = page.get_by_test_id(f"models-forget-{provider}")
        if forget.count() and forget.first.is_visible(timeout=0):
            forget.click()
    page.get_by_label("Cursor API key").fill("test-secret-cursor")
    expect(page.get_by_label("Cursor API key")).to_have_value("test-secret-cursor")
    page.get_by_test_id("models-save-cursor").click()
    expect(page.get_by_test_id("models-status-cursor")).to_contain_text("Connected", timeout=8_000)
    expect(page.get_by_test_id("models-use-cursor")).to_be_visible()
    expect(page.get_by_test_id("models-save-settings-cursor")).to_have_count(0)
    expect(page.get_by_test_id("models-empty-openrouter")).to_contain_text(
        "Paste a key on this row to load models."
    )
    expect(page.get_by_test_id("models-use-openrouter")).to_have_count(0)
    page.get_by_test_id("models-forget-cursor").click()
    expect(page.get_by_label("Cursor API key")).to_be_visible(timeout=8_000)


def test_models_chip_click_uses_that_model(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, unique_bot("ChipUse"))
    open_models(page)
    leftover = page.get_by_test_id("models-forget-cursor")
    if leftover.count() and leftover.first.is_visible(timeout=0):
        leftover.click()
        expect(page.get_by_label("Cursor API key")).to_be_visible()
    page.get_by_label("Cursor API key").fill("test-secret-cursor")
    expect(page.get_by_label("Cursor API key")).to_have_value("test-secret-cursor")
    page.get_by_test_id("models-save-cursor").click()
    expect(page.get_by_test_id("models-status-cursor")).to_contain_text("Connected", timeout=8_000)
    expect(page.get_by_test_id("models-using")).to_contain_text("scripted")
    chip = page.get_by_test_id("models-picker-cursor").locator("[data-model]").first
    expect(chip).to_be_visible()
    model_id = chip.get_attribute("data-model")
    assert model_id
    with page.expect_request(
        lambda request: request.method == "POST" and "/v1/models/default" in request.url,
        timeout=8_000,
    ) as posted:
        chip.click()
    assert model_id in (posted.value.post_data or "")
    expect(page.get_by_test_id("models-using")).to_contain_text(model_id, timeout=8_000)
    expect(chip).to_have_attribute("aria-selected", "true")


def test_models_list_error_is_not_silent(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, unique_bot("ListErr"))
    fulfill_json(page, "**/v1/models", 500, '{"detail":"list down"}', method="GET")
    open_models(page)
    expect(page.get_by_test_id("models-error")).to_contain_text("list down")


def test_models_forget_keeps_key_on_host_error(page: Page, client_url: str, host_url: str) -> None:
    pair_fresh(page, client_url, host_url)
    create_named_bot(page, unique_bot("ForgetErr"))
    open_models(page)
    leftover = page.get_by_test_id("models-forget-cursor")
    if leftover.count() and leftover.first.is_visible(timeout=0):
        leftover.click()
        expect(page.get_by_label("Cursor API key")).to_be_visible()
    page.get_by_label("Cursor API key").fill("test-secret-cursor")
    expect(page.get_by_label("Cursor API key")).to_have_value("test-secret-cursor")
    page.get_by_test_id("models-save-cursor").click()
    expect(page.get_by_test_id("models-status-cursor")).to_contain_text("Connected", timeout=8_000)
    fulfill_json(
        page, "**/v1/models/credentials/cursor", 500, '{"detail":"forget failed"}', method="DELETE"
    )
    page.get_by_test_id("models-forget-cursor").click()
    expect(page.get_by_test_id("models-error-cursor")).to_contain_text("forget failed")
    expect(page.get_by_test_id("models-status-cursor")).to_contain_text("Connected")
    expect(page.get_by_test_id("models-forget-cursor")).to_be_visible()
