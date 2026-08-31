from __future__ import annotations

import pytest

from artek_buddy.connections.broker import (
    CONNECT_START_ERROR,
    DOCS_TEXT,
    FakeBroker,
    filter_catalog,
    toolkit_no_auth,
    validate_redirect,
)


def test_filter_catalog_matches_slug_or_name() -> None:
    broker = FakeBroker()
    items = broker.catalog(None, set())
    slugs = {item.slug for item in items}
    assert slugs == {"mail", "chat", "issues", "calendar", "docs", "needssetup"}
    docs = filter_catalog(items, "DOC")
    assert [item.slug for item in docs] == ["docs"]
    assert filter_catalog(items, "zzz") == []


def test_fake_broker_docs_connects_without_browser() -> None:
    broker = FakeBroker()
    started = broker.begin("docs", "https://window.example/app")
    assert started.status == "connected"
    assert started.authorization_url is None
    assert "docs_read" in started.capabilities
    specs = broker.tool_specs(["docs"])
    assert [spec.name for spec in specs] == ["docs_read"]
    result = broker.execute("docs_read", {}, provider="docs", remote_id=started.remote_id, key="")
    assert result["ok"] is True
    assert result["text"] == DOCS_TEXT
    assert result.get("announce") is True


def test_fake_broker_mail_needs_complete_then_revoke_drops_tools() -> None:
    broker = FakeBroker()
    started = broker.begin("mail", "https://window.example/app")
    assert started.status == "pending"
    assert started.authorization_url is not None
    assert "example.test" in started.authorization_url
    assert broker.tool_specs(["mail"]) == []
    finished = broker.complete(started.remote_id)
    assert finished == "connected"
    assert [spec.name for spec in broker.tool_specs(["mail"])] == ["mail_inbox"]
    broker.revoke(started.remote_id)
    assert broker.tool_specs(["mail"]) == []
    missing = broker.execute("mail_inbox", {}, provider="mail", remote_id=started.remote_id, key="")
    assert missing["ok"] is False


def test_needssetup_begin_explains_the_next_step() -> None:
    broker = FakeBroker()
    with pytest.raises(RuntimeError, match="finish that setup"):
        broker.begin("needssetup", "https://window.example/app")
    assert CONNECT_START_ERROR.startswith("could not start that connection.")
    assert "try Connect again" in CONNECT_START_ERROR


def test_toolkit_no_auth_reads_nested_flags() -> None:
    assert toolkit_no_auth({"no_auth": True}) is True
    assert toolkit_no_auth({"toolkit": {"slug": "weather", "no_auth": True}}) is True
    assert toolkit_no_auth({"auth_schemes": ["NO_AUTH"]}) is True
    assert toolkit_no_auth({"meta": {"no_auth": True}}) is True
    assert toolkit_no_auth({"slug": "weather", "name": "Weather"}) is False


def test_validate_redirect_rejects_empty_and_non_http() -> None:
    assert validate_redirect("https://window.example/app") == "https://window.example/app"
    with pytest.raises(ValueError):
        validate_redirect("")
    with pytest.raises(ValueError):
        validate_redirect("javascript:alert(1)")
    with pytest.raises(ValueError):
        validate_redirect("https://user:pass@evil.example/")
