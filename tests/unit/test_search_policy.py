from __future__ import annotations

from artek_buddy.contracts.domain import Principal
from artek_buddy.search_policy import (
    authorized_search_resource_ids,
    normalize_search_query,
    parse_search_kinds,
    searchable_message_text,
)


def test_non_owner_gets_empty_authorized_set() -> None:
    principal = Principal(member_id="mem_guest", device_id="dev_g", role="member")
    assert authorized_search_resource_ids(principal, ["bot_a", "bot_b"], "ws_local") == []


def test_owner_includes_bots_and_workspace() -> None:
    principal = Principal(member_id="mem_owner", device_id="host", role="owner")
    assert authorized_search_resource_ids(principal, ["bot_a"], "ws_local") == ["bot_a", "ws_local"]


def test_searchable_message_text_skips_traces_and_tools() -> None:
    text = searchable_message_text(
        [
            {"kind": "progress", "text": "SECRETPROGRESS"},
            {"kind": "plugin", "text": "SECRETPLUGIN"},
            {"kind": "computer", "text": "SECRETPATH"},
            {"kind": "text", "text": "hello owner"},
            {"kind": "file", "name": "notes.txt"},
        ]
    )
    assert text == "hello owner notes.txt"
    assert "SECRET" not in text


def test_normalize_search_query_caps_length_and_tokens() -> None:
    assert normalize_search_query("  alpha   beta  ") == "alpha beta"
    assert normalize_search_query("unique-fts-token") == "unique fts token"
    assert normalize_search_query("") == ""
    long = "w" * 200
    assert len(normalize_search_query(long)) <= 80
    tokens = normalize_search_query("a b c d e f g h i j")
    assert tokens.split() == ["a", "b", "c", "d", "e", "f", "g", "h"]


def test_parse_search_kinds_drops_unknown() -> None:
    assert parse_search_kinds("message,nope,memory") == ["message", "memory"]
    assert parse_search_kinds("") == ["artifact", "bot", "memory", "message"]
