from __future__ import annotations

from types import SimpleNamespace

from artek_buddy.apps import format_apps_context
from artek_buddy.memory import wrap_turn_prompt


def test_format_apps_context_without_key() -> None:
    store = SimpleNamespace(raw_connection_key=lambda: None)
    text = format_apps_context(store)
    assert text is not None
    assert "list_apps" in text
    assert "connect_app" in text
    assert "Plugins" in text
    assert "git" in text.lower()


def test_format_apps_context_lists_connected_names_only() -> None:
    store = SimpleNamespace(
        raw_connection_key=lambda: "ak-x",
        list_connections=lambda: SimpleNamespace(
            connections=[
                SimpleNamespace(status="connected", display_name="Docs", provider="docs"),
                SimpleNamespace(status="pending", display_name="Mail", provider="mail"),
            ]
        ),
    )
    text = format_apps_context(store)
    assert text is not None
    assert "Docs" in text
    assert "Mail" not in text
    assert "Subotica" not in text
    assert "Inbox is empty" not in text
    assert "list_apps" in text
    assert "connect_app" in text
    wrapped = wrap_turn_prompt("hello", None, role="lead", apps_context=text)
    assert "<host_apps>" in wrapped
    assert "Docs" in wrapped
    assert "SECRET" not in wrapped


def test_lead_prompt_names_list_and_connect_apps() -> None:
    wrapped = wrap_turn_prompt("hi", None, role="lead")
    assert "list_apps" in wrapped
    assert "connect_app" in wrapped
    assert "git" in wrapped.lower()
