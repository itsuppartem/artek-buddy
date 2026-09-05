from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from cursor_sdk import (
    CursorAgentError,
    InternalServerError,
    NotFoundError,
    UnsupportedRunOperationError,
)

from artek_buddy.config import Settings
from artek_buddy.runtime.cursor import CursorRuntime, _is_unsupported_list_runs
from artek_buddy.runtime.types import RunRecord


class _Run:
    def __init__(self, run_id: str, *, status: str, result: str = "") -> None:
        self.id = run_id
        self._result = SimpleNamespace(status=status, result=result, store=None)

    async def events(self) -> AsyncIterator[Any]:
        if False:
            yield None

    async def wait(self) -> Any:
        return self._result

    async def text(self) -> str:
        return str(self._result.result or "")


class _Agent:
    def __init__(self, agent_id: str, runs: list[_Run]) -> None:
        self.agent_id = agent_id
        self._runs = iter(runs)
        self.send_options: list[dict[str, Any]] = []

    async def send(self, _prompt: str, options: dict[str, Any]) -> _Run:
        self.send_options.append(options)
        return next(self._runs)

    async def close(self) -> None:
        pass


class _Agents:
    def __init__(self) -> None:
        pass

    async def resume(self, _agent_id: str, _options: Any) -> _Agent:
        raise AssertionError("unexpected resume")


class _MockClient:
    def __init__(
        self,
        *,
        list_runs_fn: Any = None,
        cancel_run_fn: Any = None,
    ) -> None:
        self.agents = _Agents()
        self._list_runs_fn = list_runs_fn
        self._cancel_run_fn = cancel_run_fn
        self.cancelled: list[str] = []

    async def aclose(self) -> None:
        pass

    async def list_runs(self, agent_id: str, limit: int = 8) -> Any:
        if self._list_runs_fn is not None:
            return await self._list_runs_fn(agent_id, limit=limit)
        return SimpleNamespace(items=[])

    async def cancel_run(self, run_id: str, *, agent_id: str | None = None) -> None:
        if self._cancel_run_fn is not None:
            await self._cancel_run_fn(run_id, agent_id=agent_id)
        self.cancelled.append(run_id)


def test_is_unsupported_list_runs() -> None:
    assert _is_unsupported_list_runs(NotFoundError("not found")) is True
    assert _is_unsupported_list_runs(UnsupportedRunOperationError("list_runs")) is True
    assert _is_unsupported_list_runs(CursorAgentError("404", status=404)) is True
    assert _is_unsupported_list_runs(Exception("Bridge request failed with HTTP 404: Not Found")) is True

    fake_resp = SimpleNamespace(response=SimpleNamespace(status_code=404))
    assert _is_unsupported_list_runs(fake_resp) is True  # type: ignore[arg-type]

    fake_code = SimpleNamespace(code="not_found")
    assert _is_unsupported_list_runs(fake_code) is True  # type: ignore[arg-type]

    # Non-404 errors remain unsupported=False
    assert _is_unsupported_list_runs(InternalServerError("500", status=500)) is False
    assert _is_unsupported_list_runs(RuntimeError("network down")) is False
    assert _is_unsupported_list_runs(ValueError("bad value")) is False


@pytest.mark.asyncio
async def test_fake_404_capability_miss_is_quiet_and_stream_starts(tmp_path, caplog) -> None:
    async def fake_list_runs_404(_agent_id: str, limit: int = 8) -> Any:
        raise CursorAgentError("Bridge request failed with HTTP 404", status=404)

    client = _MockClient(list_runs_fn=fake_list_runs_404)
    agent = _Agent("agent-quiet-404", [_Run("run-1", status="completed", result="done")])

    settings = Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        cursor_api_key="ci-cursor-key",
        agent_cwd=str(tmp_path / "workspace"),
        agent_data_dir=str(tmp_path / "data"),
        sandbox_provider="fake",
    )
    runtime = CursorRuntime(client, settings)
    runtime._agents[agent.agent_id] = agent

    caplog.set_level(logging.DEBUG, logger="artek_buddy")
    output = [
        item
        async for item in runtime.stream(
            "test prompt",
            session_id=agent.agent_id,
            bot_id="bot-test",
        )
    ]

    terminal = output[-1]
    assert isinstance(terminal, RunRecord)
    assert terminal.status == "completed"
    assert terminal.result == "done"

    # Confirm NO error logs emitted for 404
    error_logs = [r for r in caplog.records if r.levelno >= logging.ERROR and r.name == "artek_buddy"]
    assert not error_logs


@pytest.mark.asyncio
async def test_other_list_failures_remain_visible(tmp_path, caplog) -> None:
    async def fake_list_runs_500(_agent_id: str, limit: int = 8) -> Any:
        raise RuntimeError("database transport broke")

    client = _MockClient(list_runs_fn=fake_list_runs_500)
    agent = _Agent("agent-err-500", [_Run("run-1", status="completed", result="done")])

    settings = Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        cursor_api_key="ci-cursor-key",
        agent_cwd=str(tmp_path / "workspace"),
        agent_data_dir=str(tmp_path / "data"),
        sandbox_provider="fake",
    )
    runtime = CursorRuntime(client, settings)
    runtime._agents[agent.agent_id] = agent

    output = [
        item
        async for item in runtime.stream(
            "test prompt",
            session_id=agent.agent_id,
            bot_id="bot-test",
        )
    ]

    terminal = output[-1]
    assert isinstance(terminal, RunRecord)
    assert terminal.status == "completed"

    # Error is logged with traceback
    error_logs = [
        r
        for r in caplog.records
        if r.levelno >= logging.ERROR and "failed to list cursor runs" in r.message
    ]
    assert len(error_logs) == 1


@pytest.mark.asyncio
async def test_supported_client_cancels_stale_runs(tmp_path, caplog) -> None:
    async def fake_list_runs_ok(_agent_id: str, limit: int = 8) -> Any:
        return SimpleNamespace(
            items=[
                SimpleNamespace(id="run-stale-1", status="running"),
                SimpleNamespace(id="run-done", status="completed"),
            ]
        )

    client = _MockClient(list_runs_fn=fake_list_runs_ok)
    agent = _Agent("agent-stale", [_Run("run-2", status="completed", result="fresh")])

    settings = Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        cursor_api_key="ci-cursor-key",
        agent_cwd=str(tmp_path / "workspace"),
        agent_data_dir=str(tmp_path / "data"),
        sandbox_provider="fake",
    )
    runtime = CursorRuntime(client, settings)
    runtime._agents[agent.agent_id] = agent

    output = [
        item
        async for item in runtime.stream(
            "test prompt",
            session_id=agent.agent_id,
            bot_id="bot-test",
        )
    ]

    terminal = output[-1]
    assert isinstance(terminal, RunRecord)
    assert terminal.status == "completed"
    assert client.cancelled == ["run-stale-1"]


@pytest.mark.asyncio
async def test_cancel_stale_run_failure_remains_visible(tmp_path, caplog) -> None:
    async def fake_list_runs_ok(_agent_id: str, limit: int = 8) -> Any:
        return SimpleNamespace(
            items=[
                SimpleNamespace(id="run-stale-2", status="running"),
            ]
        )

    async def fake_cancel_fail(_run_id: str, *, agent_id: str | None = None) -> None:
        raise RuntimeError("cancel refused by bridge")

    client = _MockClient(list_runs_fn=fake_list_runs_ok, cancel_run_fn=fake_cancel_fail)
    agent = _Agent("agent-cancel-err", [_Run("run-3", status="completed", result="ok")])

    settings = Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        cursor_api_key="ci-cursor-key",
        agent_cwd=str(tmp_path / "workspace"),
        agent_data_dir=str(tmp_path / "data"),
        sandbox_provider="fake",
    )
    runtime = CursorRuntime(client, settings)
    runtime._agents[agent.agent_id] = agent

    output = [
        item
        async for item in runtime.stream(
            "test prompt",
            session_id=agent.agent_id,
            bot_id="bot-test",
        )
    ]

    terminal = output[-1]
    assert isinstance(terminal, RunRecord)
    assert terminal.status == "completed"

    cancel_errs = [
        r
        for r in caplog.records
        if r.levelno >= logging.ERROR and "failed to cancel stale cursor run" in r.message
    ]
    assert len(cancel_errs) == 1
