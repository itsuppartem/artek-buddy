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
    if not (settings.cursor_api_key or "").strip():
        raise AgentRuntimeError("CURSOR_API_KEY is required for the cursor runtime")
    from cursor_sdk import AsyncClient
    from artek_buddy.runtime.cursor import CursorRuntime

    async with await AsyncClient.launch_bridge(workspace=settings.agent_cwd) as client:
        runtime = CursorRuntime(client, settings, store=store, computers=computers)
        await runtime.start()
        yield runtime
