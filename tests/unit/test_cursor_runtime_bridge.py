from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from cursor_sdk import AgentBusyError

from artek_buddy.config import Settings
from artek_buddy.db.shaping import TURN_FAILED
from artek_buddy.observe import bind_turn, unbind_turn
from artek_buddy.runtime.cursor import CursorRuntime
from artek_buddy.runtime.types import RunRecord

Timeline = list[tuple[str, str]]


class _Run:
    def __init__(
        self,
        run_id: str,
        *,
        status: str,
        result: str = "",
        timeline: Timeline | None = None,
        supports_cancel: bool = True,
    ) -> None:
        self.id = run_id
        self.cancelled = 0
        self._timeline = timeline
        self._supports_cancel = supports_cancel
        self._result = SimpleNamespace(
            status=status,
            result=result,
            store={"error_code": TURN_FAILED} if status == "error" else None,
        )

    def supports(self, operation: str) -> bool:
        return operation == "cancel" and self._supports_cancel

    async def events(self) -> AsyncIterator[Any]:
        if False:
            yield None

    async def wait(self) -> Any:
        if self._timeline is not None:
            self._timeline.append(("wait", self.id))
        return self._result

    async def cancel(self) -> None:
        self.cancelled += 1
        if self._timeline is not None:
            self._timeline.append(("cancel", self.id))

    async def text(self) -> str:
        return str(self._result.result or "")


class _Agent:
    def __init__(
        self,
        agent_id: str,
        runs: list[_Run],
        *,
        timeline: Timeline | None = None,
    ) -> None:
        self.agent_id = agent_id
        self._runs = iter(runs)
        self.send_options: list[dict[str, Any]] = []
        self.closed = 0
        self._timeline = timeline

    async def send(self, _prompt: str, options: dict[str, Any]) -> _Run:
        self.send_options.append(options)
        run = next(self._runs)
        if self._timeline is not None:
            self._timeline.append(("send", run.id))
        return run

    async def close(self) -> None:
        self.closed += 1


class _BusyAgent(_Agent):
    def __init__(self, agent_id: str, runs: list[_Run], *, busy_times: int) -> None:
        super().__init__(agent_id, runs)
        self.busy_times = busy_times

    async def send(self, _prompt: str, options: dict[str, Any]) -> _Run:
        self.send_options.append(options)
        if len(self.send_options) <= self.busy_times:
            raise AgentBusyError("agent busy")
        return next(self._runs)


class _Agents:
    def __init__(self, resumed: _Agent | None = None) -> None:
        self.resumed = resumed
        self.resume_ids: list[str] = []
        self.create_calls = 0

    async def create(self, *_args: Any, **_options: Any) -> _Agent:
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


def _settings(tmp_path: Any) -> Settings:
    return Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        cursor_api_key="ci-cursor-key",
        agent_cwd=str(tmp_path / "workspace"),
        agent_data_dir=str(tmp_path / "data"),
        sandbox_provider="fake",
    )


def _send_line(caplog: pytest.LogCaptureFixture, *needles: str) -> str:
    matches = [
        record.getMessage()
        for record in caplog.records
        if all(needle in record.getMessage() for needle in needles)
    ]
    assert matches, f"missing log containing {needles!r} in {caplog.text}"
    return matches[-1]


@pytest.mark.asyncio
async def test_agent_busy_retries_once_with_force(tmp_path) -> None:
    agent = _BusyAgent(
        "agent-busy",
        [_Run("run-ok", status="finished", result="ok")],
        busy_times=1,
    )
    runtime = CursorRuntime(_Client(_Agents()), _settings(tmp_path))
    runtime._agents[agent.agent_id] = agent

    output = [
        item
        async for item in runtime.stream(
            "continue",
            session_id=agent.agent_id,
            bot_id="bot-busy",
        )
    ]

    terminal = output[-1]
    assert isinstance(terminal, RunRecord)
    assert terminal.status == "completed"
    assert terminal.result == "ok"
    model = runtime.model.to_json()
    assert agent.send_options == [
        {"local": {"cwd": str(tmp_path / "workspace")}, "model": model},
        {"local": {"cwd": str(tmp_path / "workspace"), "force": True}, "model": model},
    ]


@pytest.mark.asyncio
async def test_agent_busy_second_busy_does_not_loop(tmp_path) -> None:
    agent = _BusyAgent("agent-busy-twice", [], busy_times=2)
    runtime = CursorRuntime(_Client(_Agents()), _settings(tmp_path))
    runtime._agents[agent.agent_id] = agent

    with pytest.raises(AgentBusyError):
        async for _item in runtime.stream(
            "continue",
            session_id=agent.agent_id,
            bot_id="bot-busy",
        ):
            pass

    model = runtime.model.to_json()
    assert agent.send_options == [
        {"local": {"cwd": str(tmp_path / "workspace")}, "model": model},
        {"local": {"cwd": str(tmp_path / "workspace"), "force": True}, "model": model},
    ]


@pytest.mark.asyncio
async def test_dead_wait_restarts_bridge_and_retries_same_agent(tmp_path, caplog) -> None:
    timeline: Timeline = []
    dead = _Run("run-dead", status="error", timeline=timeline)
    recovered = _Run("run-recovered", status="finished", result="recovered", timeline=timeline)
    first_agent = _Agent("agent-old", [dead], timeline=timeline)
    resumed_agent = _Agent("agent-old", [recovered], timeline=timeline)
    first_client = _Client(_Agents())
    recovered_client = _Client(_Agents(resumed_agent))
    launches = 0

    async def restart_bridge() -> _Client:
        nonlocal launches
        launches += 1
        return recovered_client

    runtime = CursorRuntime(
        first_client,
        _settings(tmp_path),
        bridge_launcher=restart_bridge,
    )
    runtime._agents[first_agent.agent_id] = first_agent
    caplog.set_level(logging.INFO, logger="artek_buddy")
    bind_turn("run_product_513", "req_513")
    try:
        output = [
            item
            async for item in runtime.stream(
                "keep working",
                session_id=first_agent.agent_id,
                bot_id="bot-workhorse",
            )
        ]
    finally:
        unbind_turn("run_product_513")

    terminal = output[-1]
    assert isinstance(terminal, RunRecord)
    assert terminal.status == "completed"
    assert terminal.result == "recovered"
    assert terminal.error is None
    assert launches == 1
    assert runtime.bridge_recycles == 1
    assert first_client.closed == 1
    assert first_agent.closed == 1
    assert first_client.agents.create_calls == 0
    assert recovered_client.agents.resume_ids == ["agent-old"]
    model = runtime.model.to_json()
    assert first_agent.send_options == [
        {"local": {"cwd": str(tmp_path / "workspace")}, "model": model},
    ]
    assert resumed_agent.send_options == [
        {"local": {"cwd": str(tmp_path / "workspace")}, "model": model},
    ]
    assert dead.cancelled == 1
    assert ("send", "run-dead") in timeline
    assert ("cancel", "run-dead") in timeline
    assert ("send", "run-recovered") in timeline
    assert timeline.index(("cancel", "run-dead")) < timeline.index(("send", "run-recovered"))
    summary = _send_line(caplog, "product_run=", "sdk_run_ids=", "retry_reason=")
    assert "product_run=run_product_513" in summary
    assert "sdk_run_ids=run-dead,run-recovered" in summary
    assert "retry_reason=dead_wait" in summary


@pytest.mark.asyncio
async def test_dead_wait_does_not_send_again_before_cancel(tmp_path) -> None:
    timeline: Timeline = []
    dead = _Run("run-dead", status="error", timeline=timeline)
    recovered = _Run("run-recovered", status="finished", result="ok", timeline=timeline)
    first_agent = _Agent("agent-old", [dead], timeline=timeline)
    resumed_agent = _Agent("agent-old", [recovered], timeline=timeline)
    launches = 0

    async def restart_bridge() -> _Client:
        nonlocal launches
        launches += 1
        return _Client(_Agents(resumed_agent))

    runtime = CursorRuntime(
        _Client(_Agents()),
        _settings(tmp_path),
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
    assert launches == 1
    send_ids = [item[1] for item in timeline if item[0] == "send"]
    assert send_ids == ["run-dead", "run-recovered"]
    assert timeline.index(("cancel", "run-dead")) < timeline.index(("send", "run-recovered"))


@pytest.mark.asyncio
async def test_dead_wait_exhausted_error_says_host_retried(tmp_path, caplog) -> None:
    timeline: Timeline = []
    first_agent = _Agent(
        "agent-old",
        [_Run("run-dead", status="error", timeline=timeline)],
        timeline=timeline,
    )
    resumed_agent = _Agent(
        "agent-old",
        [_Run("run-dead-2", status="error", timeline=timeline)],
        timeline=timeline,
    )

    async def restart_bridge() -> _Client:
        return _Client(_Agents(resumed_agent))

    runtime = CursorRuntime(
        _Client(_Agents()),
        _settings(tmp_path),
        bridge_launcher=restart_bridge,
    )
    runtime._agents[first_agent.agent_id] = first_agent
    caplog.set_level(logging.INFO, logger="artek_buddy")

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
    assert terminal.status == "failed"
    assert terminal.error is not None
    assert "retried" in terminal.error.lower()
    assert "Send again" in terminal.error
    assert timeline.index(("cancel", "run-dead")) < timeline.index(("send", "run-dead-2"))
    summary = _send_line(caplog, "sdk_run_ids=")
    assert "run-dead" in summary
    assert "run-dead-2" in summary
    assert "retry_reason=dead_wait" in summary


@pytest.mark.asyncio
async def test_job_send_includes_idempotency_key_including_force_retry(tmp_path) -> None:
    agent = _BusyAgent(
        "agent-job",
        [_Run("run-ok", status="finished", result="ok")],
        busy_times=1,
    )
    runtime = CursorRuntime(_Client(_Agents()), _settings(tmp_path))
    runtime._agents[agent.agent_id] = agent
    output = [
        item
        async for item in runtime.stream(
            "nightly",
            session_id=agent.agent_id,
            bot_id="bot-job",
            idempotency_key="job_ab12cd34",
        )
    ]
    terminal = output[-1]
    assert isinstance(terminal, RunRecord)
    assert terminal.status == "completed"
    model = runtime.model.to_json()
    cwd = {"cwd": str(tmp_path / "workspace")}
    assert agent.send_options == [
        {"local": cwd, "model": model, "idempotency_key": "job_ab12cd34"},
        {
            "local": {**cwd, "force": True},
            "model": model,
            "idempotency_key": "job_ab12cd34",
        },
    ]


@pytest.mark.asyncio
async def test_interactive_send_omits_idempotency_key(tmp_path) -> None:
    agent = _Agent("agent-chat", [_Run("run-ok", status="finished", result="ok")])
    runtime = CursorRuntime(_Client(_Agents()), _settings(tmp_path))
    runtime._agents[agent.agent_id] = agent
    output = [
        item
        async for item in runtime.stream(
            "hello",
            session_id=agent.agent_id,
            bot_id="bot-chat",
        )
    ]
    terminal = output[-1]
    assert isinstance(terminal, RunRecord)
    assert terminal.status == "completed"
    assert "idempotency_key" not in agent.send_options[0]


@pytest.mark.asyncio
async def test_job_send_keeps_idempotency_key_after_bridge_restart(tmp_path) -> None:
    first_agent = _Agent("agent-old", [_Run("run-dead", status="error")])
    resumed_agent = _Agent("agent-old", [_Run("run-recovered", status="finished", result="ok")])

    async def restart_bridge() -> _Client:
        return _Client(_Agents(resumed_agent))

    runtime = CursorRuntime(
        _Client(_Agents()),
        _settings(tmp_path),
        bridge_launcher=restart_bridge,
    )
    runtime._agents[first_agent.agent_id] = first_agent
    output = [
        item
        async for item in runtime.stream(
            "keep working",
            session_id=first_agent.agent_id,
            bot_id="bot-workhorse",
            idempotency_key="job_ab12cd34",
        )
    ]
    terminal = output[-1]
    assert isinstance(terminal, RunRecord)
    assert terminal.status == "completed"
    assert first_agent.send_options[0]["idempotency_key"] == "job_ab12cd34"
    assert resumed_agent.send_options[0]["idempotency_key"] == "job_ab12cd34"
