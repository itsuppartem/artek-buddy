from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from artek_buddy.config import Settings
from artek_buddy.db.shaping import TURN_FAILED
from artek_buddy.runtime.cursor import CursorRuntime
from artek_buddy.runtime.types import RunRecord


class _Run:
    def __init__(self, run_id: str, *, status: str, result: str = "") -> None:
        self.id = run_id
        self._result = SimpleNamespace(
            status=status,
            result=result,
            store={"error_code": TURN_FAILED} if status == "error" else None,
        )

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
        self.closed = 0

    async def send(self, _prompt: str, options: dict[str, Any]) -> _Run:
        self.send_options.append(options)
        return next(self._runs)

    async def close(self) -> None:
        self.closed += 1


class _Agents:
    def __init__(self, resumed: _Agent | None = None) -> None:
        self.resumed = resumed
        self.resume_ids: list[str] = []
        self.create_calls = 0

    async def create(self, **_options: Any) -> _Agent:
        self.create_calls += 1
        raise AssertionError("a fresh logical agent cannot heal a poisoned bridge")

    async def resume(self, agent_id: str, _options: Any) -> _Agent:
        self.resume_ids.append(agent_id)
        assert self.resumed is not None
        return self.resumed


class _Client:
    def __init__(self, agents: _Agents) -> None:
        self.agents = agents
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


@pytest.mark.asyncio
async def test_dead_wait_restarts_bridge_and_retries_same_agent(tmp_path) -> None:
    first_agent = _Agent(
        "agent-old",
        [
            _Run("run-dead", status="error"),
            _Run("run-forced", status="error"),
        ],
    )
    resumed_agent = _Agent(
        "agent-old",
        [_Run("run-recovered", status="finished", result="recovered")],
    )
    first_client = _Client(_Agents())
    recovered_client = _Client(_Agents(resumed_agent))
    launches = 0

    async def restart_bridge() -> _Client:
        nonlocal launches
        launches += 1
        return recovered_client

    settings = Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        cursor_api_key="ci-cursor-key",
        agent_cwd=str(tmp_path / "workspace"),
        agent_data_dir=str(tmp_path / "data"),
        sandbox_provider="fake",
    )
    runtime = CursorRuntime(
        first_client,
        settings,
        bridge_launcher=restart_bridge,
    )
    runtime._agents[first_agent.agent_id] = first_agent

    output = [
        item
        async for item in runtime.stream(
            "keep working",
            session_id=first_agent.agent_id,
            bot_id="bot-workhorse",
        )
    ]

    terminal = output[-1]
    assert isinstance(terminal, RunRecord)
    assert terminal.status == "completed"
    assert terminal.result == "recovered"
    assert launches == 1
    assert runtime.bridge_recycles == 1
    assert first_client.closed == 1
    assert first_agent.closed == 1
    assert first_client.agents.create_calls == 0
    assert recovered_client.agents.resume_ids == ["agent-old"]
    assert first_agent.send_options == [
        {"local": {"cwd": str(tmp_path / "workspace")}},
        {"local": {"cwd": str(tmp_path / "workspace"), "force": True}},
    ]
    assert resumed_agent.send_options == [
        {"local": {"cwd": str(tmp_path / "workspace")}},
    ]
