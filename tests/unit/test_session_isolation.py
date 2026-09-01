from __future__ import annotations

import asyncio

from artek_buddy.config import Settings
from artek_buddy.runtime.http_chat import HttpChatRuntime
from artek_buddy.runtime.scripted import ScriptedRuntime


def _settings(tmp_path, runtime: str = "scripted") -> Settings:
    return Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        agent_runtime=runtime,
        sandbox_provider="fake",
        agent_data_dir=str(tmp_path / "data"),
        agent_cwd=str(tmp_path / "cwd"),
    )


def test_ensure_session_does_not_share_default_across_bots(tmp_path) -> None:
    async def inner() -> None:
        runtime = ScriptedRuntime(_settings(tmp_path))
        first = await runtime.ensure_session(None, name="Workhorse", bot_id="bot_a")
        second = await runtime.ensure_session(None, name="Vacancies", bot_id="bot_b")
        assert first != second
        assert runtime._bot_by_agent[first] == "bot_a"
        assert runtime._bot_by_agent[second] == "bot_b"
        stolen = await runtime.ensure_session(first, name="Other", bot_id="bot_c")
        assert stolen != first
        assert stolen != second
        assert runtime._bot_by_agent[first] == "bot_a"
        assert runtime._bot_by_agent[stolen] == "bot_c"

    asyncio.run(inner())


def test_http_chat_ensure_session_keeps_bots_apart(tmp_path) -> None:
    async def inner() -> None:
        runtime = HttpChatRuntime(_settings(tmp_path, runtime="cursor"))
        first = await runtime.ensure_session(None, name="A", bot_id="bot_a")
        second = await runtime.ensure_session(None, name="B", bot_id="bot_b")
        assert first != second
        stolen = await runtime.ensure_session(first, name="C", bot_id="bot_c")
        assert stolen != first

    asyncio.run(inner())
