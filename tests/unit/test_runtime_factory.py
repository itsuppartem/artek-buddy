from __future__ import annotations

import pytest

from artek_buddy.config import Settings
from artek_buddy.runtime.factory import open_runtime, runtime_kind
from artek_buddy.runtime.scripted import E2E_FAIL_ERROR, steps_for_prompt
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
async def test_unknown_runtime_and_missing_cursor_key() -> None:
    with pytest.raises(AgentRuntimeError, match="unknown"):
        async with open_runtime(_settings("nope")):
            pass
    with pytest.raises(AgentRuntimeError, match="CURSOR_API_KEY"):
        async with open_runtime(_settings("cursor", key="")):
            pass


def test_scripted_fail_and_default_steps() -> None:
    fail = steps_for_prompt("please e2e-fail now")
    assert fail[-1].status == "failed"
    assert fail[-1].error == E2E_FAIL_ERROR
    ok = steps_for_prompt("plain hello")
    assert ok[-1].status == "completed" or ok[-1].result == "ok"
