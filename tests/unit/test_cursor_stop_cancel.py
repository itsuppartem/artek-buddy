from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from cursor_sdk import CursorAgentError

from artek_buddy.config import Settings
from artek_buddy.runtime.cursor import CursorRuntime, _is_agent_busy_error
from artek_buddy.runtime.types import AgentRuntimeError, RunRecord


class _CompletedRun:
    def __init__(self, run_id: str, *, result: str = "ok") -> None:
        self.id = run_id
        self._result = SimpleNamespace(status="finished", result=result, store=None)

    async def events(self) -> AsyncIterator[Any]:
        if False:
            yield None

    async def wait(self) -> Any:
        return self._result

    async def text(self) -> str:
        return str(self._result.result or "")


class _HangingRun:
    def __init__(self, run_id: str, started: asyncio.Event) -> None:
        self.id = run_id
        self.started = started
        self.cancel_calls = 0
        self.stop_calls = 0
        self.abort_calls = 0

    def supports(self, operation: str) -> bool:
        return operation == "cancel"

    async def cancel(self) -> None:
        self.cancel_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def abort(self) -> None:
        self.abort_calls += 1

    async def events(self) -> AsyncIterator[Any]:
        self.started.set()
        await asyncio.sleep(3600)
        if False:
            yield None

    async def wait(self) -> Any:
        raise AssertionError("wait should not run while events hang")

    async def text(self) -> str:
        return ""


class _Agent:
    def __init__(self, agent_id: str, send_impl: Any) -> None:
        self.agent_id = agent_id
        self._send_impl = send_impl
        self.send_options: list[dict[str, Any]] = []

    async def send(self, _prompt: str, options: dict[str, Any]) -> Any:
        self.send_options.append(options)
        return await self._send_impl(options)

    async def close(self) -> None:
        return None


class _Client:
    def __init__(self) -> None:
        self.agents = SimpleNamespace()

    async def aclose(self) -> None:
        return None


def _settings(tmp_path: Any) -> Settings:
    return Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        cursor_api_key="ci-cursor-key",
        agent_cwd=str(tmp_path / "workspace"),
        agent_data_dir=str(tmp_path / "data"),
        sandbox_provider="fake",
    )


def _runtime(tmp_path: Any, agent: _Agent) -> CursorRuntime:
    runtime = CursorRuntime(_Client(), _settings(tmp_path))
    runtime._agents[agent.agent_id] = agent
    return runtime


def test_is_agent_busy_error_matches_already_active_run() -> None:
    assert (
        _is_agent_busy_error(CursorAgentError("Agent x already has active run", is_retryable=False))
        is True
    )
    assert (
        _is_agent_busy_error(CursorAgentError("ALREADY HAS ACTIVE RUN", is_retryable=False)) is True
    )
    assert _is_agent_busy_error(CursorAgentError("model not found", is_retryable=False)) is False


@pytest.mark.asyncio
async def test_cancelling_stream_after_send_calls_run_cancel(tmp_path) -> None:
    started = asyncio.Event()
    hanging = _HangingRun("run-live", started)

    async def send_impl(_options: dict[str, Any]) -> _HangingRun:
        return hanging

    agent = _Agent("agent-stop", send_impl)
    runtime = _runtime(tmp_path, agent)

    async def consume() -> None:
        async for _item in runtime.stream(
            "long turn",
            session_id=agent.agent_id,
            bot_id="bot-stop",
        ):
            pass

    task = asyncio.create_task(consume())
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert hanging.cancel_calls == 1
    assert hanging.stop_calls == 0
    assert hanging.abort_calls == 0


@pytest.mark.asyncio
async def test_already_active_run_retries_once_with_force(tmp_path) -> None:
    sends = 0
    completed = _CompletedRun("run-ok", result="fresh")

    async def send_impl(options: dict[str, Any]) -> _CompletedRun:
        nonlocal sends
        sends += 1
        if sends == 1:
            raise CursorAgentError("Agent x already has active run", is_retryable=False)
        assert options.get("local", {}).get("force") is True
        return completed

    agent = _Agent("agent-busy", send_impl)
    runtime = _runtime(tmp_path, agent)

    output = [
        item
        async for item in runtime.stream(
            "next prompt",
            session_id=agent.agent_id,
            bot_id="bot-busy",
        )
    ]

    terminal = output[-1]
    assert isinstance(terminal, RunRecord)
    assert terminal.status == "completed"
    assert terminal.result == "fresh"
    assert sends == 2
    assert len(agent.send_options) == 2
    assert "force" not in agent.send_options[0].get("local", {})
    assert agent.send_options[1].get("local", {}).get("force") is True


@pytest.mark.asyncio
async def test_second_already_active_run_still_fails(tmp_path) -> None:
    sends = 0

    async def send_impl(_options: dict[str, Any]) -> _CompletedRun:
        nonlocal sends
        sends += 1
        raise CursorAgentError("Agent x already has active run", is_retryable=False)

    agent = _Agent("agent-busy-twice", send_impl)
    runtime = _runtime(tmp_path, agent)

    with pytest.raises(AgentRuntimeError, match="already has active run"):
        async for _item in runtime.stream(
            "next prompt",
            session_id=agent.agent_id,
            bot_id="bot-busy-twice",
        ):
            pass

    assert sends == 2
    assert "force" not in agent.send_options[0].get("local", {})
    assert agent.send_options[1].get("local", {}).get("force") is True
