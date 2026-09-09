from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from artek_buddy.config import Settings
from artek_buddy.runtime.protocol import AgentRuntime
from artek_buddy.runtime.scripted import ScriptedRuntime
from artek_buddy.runtime.types import AgentRuntimeError


def runtime_kind(settings: Settings) -> str:
    kind = (getattr(settings, "agent_runtime", None) or "cursor").strip().lower()
    return kind or "cursor"


class _TimeoutBoundClient:
    """`with_options` view plus the launch owner so `aclose` still stops the bridge."""

    __slots__ = ("_owner", "_view")

    def __init__(self, owner: Any, view: Any) -> None:
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_view", view)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._view, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"_owner", "_view"}:
            object.__setattr__(self, name, value)
            return
        setattr(self._view, name, value)

    async def aclose(self) -> None:
        close = getattr(self._owner, "aclose", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                await result
            return
        sync = getattr(self._owner, "close", None)
        if callable(sync):
            sync()


def apply_cursor_client_options(client: Any, settings: Settings) -> Any:
    apply = getattr(client, "with_options", None)
    if not callable(apply):
        return client
    view = apply(
        unary_timeout=settings.cursor_unary_timeout_s,
        stream_timeout=settings.cursor_stream_timeout_s,
        max_retries=settings.cursor_max_retries,
    )
    if view is None or view is client:
        return client
    return _TimeoutBoundClient(client, view)


async def launch_cursor_bridge(
    settings: Settings,
    *,
    launcher: Callable[..., Awaitable[Any]] | None = None,
) -> Any:
    launch = launcher
    if launch is None:
        from cursor_sdk import AsyncClient

        launch = AsyncClient.launch_bridge
    raw = await launch(workspace=settings.agent_cwd)
    return apply_cursor_client_options(raw, settings)


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
    from artek_buddy.runtime.cursor import CursorRuntime

    async def launch_bridge() -> Any:
        return await launch_cursor_bridge(settings)

    client = await launch_bridge()
    runtime = CursorRuntime(
        client,
        settings,
        store=store,
        computers=computers,
        bridge_launcher=launch_bridge,
    )
    try:
        await runtime.start()
        yield runtime
    finally:
        await runtime.aclose()
