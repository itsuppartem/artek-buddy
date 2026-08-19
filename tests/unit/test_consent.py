from __future__ import annotations

from artek_buddy.consent import (
    browse_origin,
    decision_from_label,
    owner_command_is_readonly,
    owner_scope,
)


def test_decision_from_label_happy_and_fail() -> None:
    assert decision_from_label("Allow once") == "once"
    assert decision_from_label("Always") == "always"
    assert decision_from_label("Deny") == "deny"
    assert decision_from_label("maybe later") is None


def test_browse_origin_requires_http_host() -> None:
    assert browse_origin("https://example.com/path") == "https://example.com"
    assert browse_origin("www.example.com") == "https://www.example.com"
    assert browse_origin("not a url") is None
    assert browse_origin("") is None


def test_owner_scope_uses_parent() -> None:
    assert owner_scope("~/notes.txt") == "~"
    assert owner_scope("/home/artek/a/b") == "/home/artek/a"


def test_owner_readonly_commands() -> None:
    assert owner_command_is_readonly("ls -la ~") is True
    assert owner_command_is_readonly("cat notes.txt") is True
    assert owner_command_is_readonly("rm -rf ~") is False
    assert owner_command_is_readonly("echo hi > file") is False
    assert owner_command_is_readonly("git status") is True
    assert owner_command_is_readonly("git commit -am x") is False
