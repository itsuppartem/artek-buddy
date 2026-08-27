from __future__ import annotations

import pytest

from artek_buddy.config import Settings
from artek_buddy.runtime.factory import open_runtime, runtime_kind
from artek_buddy.runtime.scripted import (
    E2E_ASK_FREE_QUESTION,
    E2E_CARD_VALUE,
    E2E_CHILD_ARCHIVED,
    E2E_FAIL_ERROR,
    E2E_HANG_S,
    E2E_META_TEXT,
    E2E_OLDER_COUNT,
    E2E_SUBAGENT_NAME,
    steps_for_prompt,
)
from artek_buddy.runtime.types import AgentRuntimeError


def _settings(runtime: str, key: str = "") -> Settings:
    return Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        agent_runtime=runtime,
        cursor_api_key=key,
        sandbox_provider="fake",
    )


def test_runtime_kind_defaults_and_scripted() -> None:
    assert runtime_kind(_settings("scripted")) == "scripted"
    assert runtime_kind(_settings("cursor")) == "cursor"


@pytest.mark.asyncio
async def test_unknown_runtime_and_cursor_boots_without_key(tmp_path) -> None:
    with pytest.raises(AgentRuntimeError, match="unknown"):
        async with open_runtime(_settings("nope")):
            pass
    empty = Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        agent_runtime="cursor",
        cursor_api_key="",
        sandbox_provider="fake",
        agent_data_dir=str(tmp_path / "data"),
        agent_cwd=str(tmp_path / "cwd"),
    )
    async with open_runtime(empty) as runtime:
        assert runtime.default_agent_id


def test_scripted_fail_and_default_steps() -> None:
    fail = steps_for_prompt("please e2e-fail now")
    assert fail[-1].status == "failed"
    assert fail[-1].error == E2E_FAIL_ERROR
    ok = steps_for_prompt("plain hello")
    assert ok[-1].status == "completed" or ok[-1].result == "ok"


def test_scripted_thread_prompts_force_window_blocks() -> None:
    blocks = steps_for_prompt("please e2e-thread-blocks")
    assert blocks[0].blocks is not None
    assert [item["kind"] for item in blocks[0].blocks] == [
        "meta",
        "progress",
        "card",
        "text",
        "computer",
        "child_bot",
        "child_bot",
    ]
    assert any(item.get("text") == E2E_META_TEXT for item in blocks[0].blocks)
    assert any(item.get("bot_id") == "$new" for item in blocks[0].blocks)
    assert any(item.get("name") == E2E_CHILD_ARCHIVED for item in blocks[0].blocks)
    assert any(
        item.get("kind") == "card" and item["lines"][0]["v"] == E2E_CARD_VALUE
        for item in blocks[0].blocks
    )

    free = steps_for_prompt("please e2e-ask-free")
    assert free[0].blocks is not None
    assert free[0].blocks[0]["text"] == E2E_ASK_FREE_QUESTION
    assert not free[0].blocks[0].get("actions")

    hang = steps_for_prompt("please e2e-hang now")
    assert hang[0].delay_s == E2E_HANG_S

    worker = steps_for_prompt("please e2e-subagent")
    assert worker[0].tool == "spawn_subagent"
    assert worker[0].args["name"] == E2E_SUBAGENT_NAME

    ask = steps_for_prompt("please e2e-ask-bot KnowsPeer | what city do you know")
    assert ask[0].tool == "message_bot"
    assert ask[0].args["bot"] == "KnowsPeer"
    assert ask[0].args["text"] == "what city do you know"

    plugin = steps_for_prompt("please e2e-plugin-docs")
    assert plugin[0].tool == "docs_read"
    asked = steps_for_prompt("please use Docs")
    assert asked[0].tool == "docs_read"
    listed = steps_for_prompt("please e2e-list-apps")
    assert listed[0].tool == "list_apps"
    assert listed[0].args.get("q") == "docs"
    attached = steps_for_prompt("please e2e-connect-docs")
    assert attached[0].tool == "connect_app"
    assert attached[0].args.get("slug") == "docs"
    mail = steps_for_prompt("please e2e-connect-mail")
    assert mail[0].tool == "connect_app"
    assert mail[0].args.get("slug") == "mail"
    twice = steps_for_prompt("please e2e-remember-twice")
    assert twice[0].tool == "remember"
    assert twice[1].tool == "remember"
    assert twice[0].args.get("content") != twice[1].args.get("content")

    taught = steps_for_prompt("please e2e-install-book")
    assert taught[0].consent is not None
    assert taught[1].tool == "install_book"
    assert taught[1].args.get("url")
    ran = steps_for_prompt("please run Invoice")
    assert ran[0].tool == "open_book"
    assert ran[0].args["name"] == "Invoice"
    dropped = steps_for_prompt("please e2e-forget-book")
    assert dropped[0].tool == "forget_book"

    older = steps_for_prompt("please e2e-load-earlier")
    assert len([step for step in older if step.blocks]) == E2E_OLDER_COUNT

    takeover = steps_for_prompt("please e2e-takeover")
    assert takeover[0].tool == "request_takeover"
    assert not any(step.result == "need you" for step in takeover)

    parked = steps_for_prompt("please e2e-park-takeover")
    assert parked[0].tool == "request_takeover"
    assert "Pass the site check" in parked[0].args["reason"]

    released = steps_for_prompt("The owner released the desktop. Continue the same task.")
    assert released[0].result == "continuing after takeover"
