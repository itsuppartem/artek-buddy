from __future__ import annotations

from types import SimpleNamespace

from artek_buddy.bot_asks import (
    ASK_REPLY_MARK,
    ASKED_YOU_MARK,
    BotAskError,
    find_inbox_bot,
    format_other_bots,
    inbound_model_prompt,
    inbound_visible_text,
    last_bot_reply,
    ready_visible_text,
    reply_model_prompt,
    resolve_ask,
)


class _Store:
    def __init__(self, bots: list[SimpleNamespace]) -> None:
        self._bots = bots

    def get_bot(self, bot_id: str) -> SimpleNamespace | None:
        return next((item for item in self._bots if item.id == bot_id), None)

    def list_bots(self) -> list[SimpleNamespace]:
        return [item for item in self._bots if item.archived_at is None]


def _bot(bot_id: str, name: str, archived: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=bot_id, name=name, archived_at="2026-01-01" if archived else None)


def test_find_inbox_bot_by_id_or_exact_name() -> None:
    store = _Store([_bot("bot_a", "Asker"), _bot("bot_b", "Knows")])
    assert find_inbox_bot(store, "bot_b").id == "bot_b"
    assert find_inbox_bot(store, "Knows").id == "bot_b"
    assert find_inbox_bot(store, "knows") is None
    assert find_inbox_bot(store, "bot_missing") is None


def test_find_inbox_bot_skips_archived_even_by_id() -> None:
    store = _Store([_bot("bot_old", "Old", archived=True)])
    assert find_inbox_bot(store, "bot_old") is None
    assert find_inbox_bot(store, "Old") is None


def test_resolve_ask_rejects_empty_self_and_missing() -> None:
    source = _bot("bot_a", "Asker")
    dest = _bot("bot_b", "Knows")
    store = _Store([source, dest, _bot("bot_old", "Old", archived=True)])
    try:
        resolve_ask(store, source, "", "Knows")
        raise AssertionError("empty text must fail")
    except BotAskError as err:
        assert err.status == 400
    try:
        resolve_ask(store, source, "hi", "Asker")
        raise AssertionError("self by name must fail")
    except BotAskError as err:
        assert err.status == 400
    try:
        resolve_ask(store, source, "hi", "bot_a")
        raise AssertionError("self by id must fail")
    except BotAskError as err:
        assert err.status == 400
    try:
        resolve_ask(store, source, "hi", "gone")
        raise AssertionError("missing must fail")
    except BotAskError as err:
        assert err.status == 404
    try:
        resolve_ask(store, source, "hi", "bot_old")
        raise AssertionError("archived must fail")
    except BotAskError as err:
        assert err.status == 404
    found = resolve_ask(store, source, "what city?", "Knows")
    assert found.id == "bot_b"


def test_last_bot_reply_skips_tool_and_computer_cards() -> None:
    messages = [
        SimpleNamespace(
            role="user",
            blocks=[{"kind": "text", "text": "Asker asked: what city?"}],
        ),
        SimpleNamespace(
            role="bot",
            blocks=[
                {"kind": "progress", "text": "searching"},
                {"kind": "computer", "state": "done", "text": "Opened Chromium"},
                {"kind": "subagent", "name": "worker", "task": "look", "status": "completed"},
                {"kind": "text", "text": "I am ready to answer. The city is Subotica."},
            ],
        ),
    ]
    assert last_bot_reply(messages) == "I am ready to answer. The city is Subotica."
    assert "Chromium" not in last_bot_reply(messages)
    assert last_bot_reply(messages, limit=10) == "I am ready"


def test_ask_prompts_carry_markers_without_the_other_thread() -> None:
    inbound = inbound_model_prompt("Asker", "what city do you know")
    assert ASKED_YOU_MARK in inbound
    assert inbound.strip().endswith("what city do you know")
    assert "whole thread" in inbound.lower() or "copy" in inbound.lower()
    visible = inbound_visible_text("Asker", "what city do you know")
    assert "Asker" in visible
    assert "what city do you know" in visible
    reply = reply_model_prompt("Knows", "The city is Subotica.")
    assert ASK_REPLY_MARK in reply
    assert "Subotica" in reply
    assert ready_visible_text("Knows")
    line = format_other_bots([_bot("bot_a", "Asker"), _bot("bot_b", "Knows")], "bot_a")
    assert "Knows" in line
    assert "Asker" not in line
    assert format_other_bots([_bot("bot_a", "Asker")], "bot_a") == ""
