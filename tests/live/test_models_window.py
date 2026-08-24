from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from tests.live.helpers import (
    composer,
    create_named_bot,
    ensure_model,
    open_models,
    pair_fresh,
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
    expect(page.get_by_test_id("models-save-openrouter")).to_be_disabled()
    expect(page.get_by_test_id("models-forget-openrouter")).to_have_count(0)
    expect(page.get_by_label("OpenRouter model")).to_be_disabled()
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
    page.get_by_test_id("models-forget-openrouter").click()
    expect(page.get_by_label("OpenRouter API key")).to_be_visible(timeout=8_000)
    expect(page.get_by_test_id("models-forget-openrouter")).to_have_count(0)
    page.get_by_role("button", name="Close Models").click()
    expect(page.get_by_test_id("needs-model")).to_be_visible(timeout=8_000)
