from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from artek_buddy.config import Settings
from artek_buddy.runtime.protocol import AgentRuntime
from artek_buddy.runtime.scripted import ScriptedRuntime
from artek_buddy.runtime.types import AgentRuntimeError


def runtime_kind(settings: Settings) -> str:
    kind = (getattr(settings, "agent_runtime", None) or "cursor").strip().lower()
    return kind or "cursor"


@asynccontextmanager
async def open_runtime(
    settings: Settings,
    store: Any | None = None,
    computers: Any | None = None,
) -> AsyncIterator[AgentRuntime]:
    kind = runtime_kind(settings)
    if kind == "scripted":
        runtime = ScriptedRuntime(settings, store=store, computers=computers)
        await runtime.start()
        yield runtime
        return
    if kind != "cursor":
        raise AgentRuntimeError(f"unknown agent runtime {kind!r}")
    key = (settings.cursor_api_key or "").strip()
    if not key and store is not None:
        try:
            key = (store.raw_key("cursor") or "").strip()
        except Exception:
            key = ""
    if not key:
        from artek_buddy.runtime.http_chat import HttpChatRuntime

        runtime = HttpChatRuntime(settings, store=store, computers=computers)
        await runtime.start()
        yield runtime
        return
    from cursor_sdk import AsyncClient

    from artek_buddy.runtime.cursor import CursorRuntime

    async with await AsyncClient.launch_bridge(workspace=settings.agent_cwd) as client:
        runtime = CursorRuntime(client, settings, store=store, computers=computers)
        await runtime.start()
        yield runtime
