from __future__ import annotations

import pytest
from pydantic import ValidationError

from artek_buddy.config import Settings


def _settings(**overrides: object) -> Settings:
    values = {
        "agent_http_token": "ci-host-token-aabbccddeeff001122334455",
        "agent_runtime": "scripted",
        "sandbox_provider": "fake",
        "cursor_api_key": "",
    }
    values.update(overrides)
    return Settings(**values)


def test_settings_accepts_non_placeholder_token() -> None:
    settings = _settings()
    assert settings.agent_runtime == "scripted"
    assert settings.sandbox_provider == "fake"
    assert settings.credential_broker_url == "http://127.0.0.1:8431"
    assert settings.credential_broker_token == ""
    assert settings.cursor_unary_timeout_s == 60.0
    assert settings.cursor_stream_timeout_s == 600.0
    assert settings.cursor_max_retries == 1


@pytest.mark.parametrize("value", ["", "change-me", "token", "secret", "password"])
def test_settings_rejects_placeholder_host_token(value: str) -> None:
    with pytest.raises(ValidationError):
        _settings(agent_http_token=value)


@pytest.mark.parametrize("field", ["cursor_unary_timeout_s", "cursor_stream_timeout_s"])
def test_settings_rejects_non_positive_cursor_timeouts(field: str) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: 0})


def test_settings_rejects_negative_cursor_retries() -> None:
    with pytest.raises(ValidationError):
        _settings(cursor_max_retries=-1)
