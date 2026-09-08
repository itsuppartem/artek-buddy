from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from cursor_sdk import AgentBusyError, CursorAgentError

from artek_buddy.config import Settings
from artek_buddy.db.shaping import TURN_FAILED, owner_visible_error
from artek_buddy.runtime.cursor import CursorRuntime
from artek_buddy.runtime.cursor_errors import (
    CURSOR_KEY_INVALID_TEXT,
    QUOTA_EXHAUSTED_TEXT,
)
from artek_buddy.runtime.types import AgentRuntimeError, AgentRuntimeExhausted, RunRecord


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


class _RunRaisesOnEvents(_Run):
    def __init__(self, run_id: str, err: BaseException) -> None:
        super().__init__(run_id, status="error")
        self._err = err

    async def events(self) -> AsyncIterator[Any]:
        raise self._err
        if False:
            yield None


class _Agent:
    def __init__(self, agent_id: str, outcomes: list[Any]) -> None:
        self.agent_id = agent_id
        self._outcomes = list(outcomes)
        self.send_options: list[dict[str, Any]] = []

    async def send(self, _prompt: str, options: dict[str, Any]) -> _Run:
        self.send_options.append(options)
        item = self._outcomes.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def close(self) -> None:
        pass


class _Client:
    def __init__(self) -> None:
        self.agents = SimpleNamespace()

    async def aclose(self) -> None:
        pass


class _DuckSdkError(CursorAgentError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        retry_after: Any = None,
        is_retryable: bool = True,
        request_id: str | None = None,
    ) -> None:
        try:
            super().__init__(message, status=status)
        except TypeError:
            super().__init__(message)
        self._duck_retry_after = retry_after
        self._duck_retryable = is_retryable
        self._duck_request_id = request_id
        self.message = message
        if status is not None and getattr(self, "status", None) is None:
            try:
                self.status = status
            except (AttributeError, TypeError):
                pass

    @property
    def retry_after(self) -> Any:
        return self._duck_retry_after

    @property
    def is_retryable(self) -> bool:
        return self._duck_retryable

    @property
    def request_id(self) -> str | None:
        return self._duck_request_id


def _sdk_type(name: str) -> type | None:
    import cursor_sdk as sdk

    cls = getattr(sdk, name, None)
    return cls if isinstance(cls, type) else None


def _make_sdk_error(
    cls: type,
    message: str,
    *,
    status: int | None,
    retry_after: Any = None,
    is_retryable: bool = True,
    request_id: str | None = None,
) -> BaseException:
    try:
        err = cls(message, status=status)
    except TypeError:
        err = cls(message)
    for name, value in (
        ("retry_after", retry_after),
        ("is_retryable", is_retryable),
        ("request_id", request_id),
        ("status", status),
        ("message", message),
    ):
        if value is None and name != "retry_after":
            continue
        try:
            setattr(err, name, value)
        except (AttributeError, TypeError):
            pass
    retryable_ok = bool(getattr(err, "is_retryable", is_retryable)) == bool(is_retryable)
    retry_after_ok = getattr(err, "retry_after", None) == retry_after
    if retryable_ok and retry_after_ok:
        return err
    return _DuckSdkError(
        message,
        status=status,
        retry_after=retry_after,
        is_retryable=is_retryable,
        request_id=request_id,
    )


def make_rate_limit(
    *,
    retry_after: Any = 0,
    is_retryable: bool = True,
    request_id: str = "req-quota",
) -> BaseException:
    cls = _sdk_type("RateLimitError") or CursorAgentError
    return _make_sdk_error(
        cls,
        "rate limited",
        status=429,
        retry_after=retry_after,
        is_retryable=is_retryable,
        request_id=request_id,
    )


def make_auth(*, request_id: str = "req-auth") -> BaseException:
    cls = _sdk_type("AuthenticationError") or CursorAgentError
    return _make_sdk_error(
        cls,
        "Authentication error invalid API key",
        status=401,
        retry_after=None,
        is_retryable=False,
        request_id=request_id,
    )


def make_busy() -> BaseException:
    try:
        return AgentBusyError("agent busy")
    except TypeError:
        return AgentBusyError("agent busy", status=409)


def make_permanent() -> BaseException:
    return _DuckSdkError(
        "not retryable",
        status=400,
        retry_after=None,
        is_retryable=False,
        request_id="req-perm",
    )


def _runtime(tmp_path, agent: _Agent) -> CursorRuntime:
    settings = Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        cursor_api_key="ci-cursor-key",
        agent_cwd=str(tmp_path / "workspace"),
        agent_data_dir=str(tmp_path / "data"),
        sandbox_provider="fake",
    )
    runtime = CursorRuntime(_Client(), settings)
    runtime._agents[agent.agent_id] = agent
    return runtime


async def _consume(runtime: CursorRuntime, agent_id: str) -> list[Any]:
    return [
        item
        async for item in runtime.stream(
            "keep working",
            session_id=agent_id,
            bot_id="bot-quota",
        )
    ]


@pytest.fixture
def instant_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []

    async def _sleep(delay: float = 0, *_args: Any, **_kwargs: Any) -> None:
        slept.append(float(delay))

    monkeypatch.setattr("artek_buddy.runtime.cursor.asyncio.sleep", _sleep)
    return slept


@pytest.mark.asyncio
async def test_rate_limit_with_retry_after_waits_then_completes(tmp_path, instant_sleep) -> None:
    agent = _Agent(
        "agent-quota-ok",
        [
            make_rate_limit(retry_after=0),
            _Run("run-ok", status="completed", result="ok"),
        ],
    )
    runtime = _runtime(tmp_path, agent)

    output = await _consume(runtime, agent.agent_id)

    terminal = output[-1]
    assert isinstance(terminal, RunRecord)
    assert terminal.status == "completed"
    assert terminal.result == "ok"
    assert len(agent.send_options) == 2
    assert "force" not in agent.send_options[0]["local"]
    assert "force" not in agent.send_options[1]["local"]
    assert instant_sleep == [0.0]
    assert runtime.bridge_recycles == 0


@pytest.mark.asyncio
async def test_still_limited_after_one_retry_is_exhausted_not_turn_failed(
    tmp_path, instant_sleep
) -> None:
    agent = _Agent(
        "agent-quota-out",
        [
            make_rate_limit(retry_after=0.01, request_id="req-first"),
            make_rate_limit(retry_after=0.01, request_id="req-second"),
        ],
    )
    runtime = _runtime(tmp_path, agent)

    with pytest.raises(AgentRuntimeExhausted) as caught:
        await _consume(runtime, agent.agent_id)

    err = caught.value
    assert err.category == "exhausted"
    assert err.retryable is True
    assert err.message == QUOTA_EXHAUSTED_TEXT
    assert err.message != TURN_FAILED
    assert owner_visible_error(err.message) == QUOTA_EXHAUSTED_TEXT
    assert owner_visible_error(err.message) != TURN_FAILED
    assert len(agent.send_options) == 2
    assert instant_sleep == [0.01]
    assert runtime.bridge_recycles == 0


@pytest.mark.asyncio
async def test_auth_error_is_not_retried_as_a_rate_limit(tmp_path, instant_sleep) -> None:
    agent = _Agent("agent-bad-key", [make_auth()])
    runtime = _runtime(tmp_path, agent)

    with pytest.raises(AgentRuntimeError) as caught:
        await _consume(runtime, agent.agent_id)

    err = caught.value
    assert not isinstance(err, AgentRuntimeExhausted)
    assert err.category == "permanent"
    assert err.retryable is False
    assert err.message == CURSOR_KEY_INVALID_TEXT
    assert "Models" in err.message
    assert err.message != TURN_FAILED
    assert owner_visible_error(err.message) == CURSOR_KEY_INVALID_TEXT
    assert len(agent.send_options) == 1
    assert instant_sleep == []
    assert runtime.bridge_recycles == 0


@pytest.mark.asyncio
async def test_agent_busy_retries_once_with_local_force(tmp_path, instant_sleep) -> None:
    agent = _Agent(
        "agent-busy",
        [
            make_busy(),
            _Run("run-forced", status="completed", result="ok"),
        ],
    )
    runtime = _runtime(tmp_path, agent)

    output = await _consume(runtime, agent.agent_id)

    terminal = output[-1]
    assert isinstance(terminal, RunRecord)
    assert terminal.status == "completed"
    assert terminal.result == "ok"
    assert len(agent.send_options) == 2
    assert "force" not in agent.send_options[0]["local"]
    assert agent.send_options[1]["local"].get("force") is True
    assert instant_sleep == []
    assert runtime.bridge_recycles == 0


@pytest.mark.asyncio
async def test_non_retryable_cursor_error_is_not_retried(tmp_path, instant_sleep) -> None:
    agent = _Agent("agent-permanent", [make_permanent()])
    runtime = _runtime(tmp_path, agent)

    with pytest.raises(AgentRuntimeError) as caught:
        await _consume(runtime, agent.agent_id)

    err = caught.value
    assert not isinstance(err, AgentRuntimeExhausted)
    assert err.retryable is False
    assert err.message != TURN_FAILED
    assert len(agent.send_options) == 1
    assert instant_sleep == []


@pytest.mark.asyncio
async def test_non_retryable_rate_limit_is_exhausted_without_retry(tmp_path, instant_sleep) -> None:
    agent = _Agent(
        "agent-quota-locked",
        [make_rate_limit(retry_after=0, is_retryable=False)],
    )
    runtime = _runtime(tmp_path, agent)

    with pytest.raises(AgentRuntimeExhausted) as caught:
        await _consume(runtime, agent.agent_id)

    assert caught.value.message == QUOTA_EXHAUSTED_TEXT
    assert caught.value.retryable is True
    assert len(agent.send_options) == 1
    assert instant_sleep == []


@pytest.mark.asyncio
async def test_rate_limit_after_send_began_does_not_start_a_second_run(
    tmp_path, instant_sleep
) -> None:
    agent = _Agent(
        "agent-billed",
        [_RunRaisesOnEvents("run-started", make_rate_limit(retry_after=0))],
    )
    runtime = _runtime(tmp_path, agent)

    with pytest.raises(AgentRuntimeExhausted) as caught:
        await _consume(runtime, agent.agent_id)

    assert caught.value.message == QUOTA_EXHAUSTED_TEXT
    assert len(agent.send_options) == 1
    assert instant_sleep == []
