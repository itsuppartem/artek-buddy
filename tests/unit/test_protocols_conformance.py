from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from artek_buddy.computer.capabilities import ComputerCapabilities
from artek_buddy.computer.client import FakeSupervisorClient, SupervisorClient
from artek_buddy.computer.protocol import ComputerGateway, SupervisorGateway
from artek_buddy.computer.service import (
    ComputerBusy,
    ComputerCancelled,
    ComputerError,
    ComputerService,
    ComputerTimeout,
    ComputerUnavailable,
)
from artek_buddy.config import Settings
from artek_buddy.contracts.domain import Bot
from artek_buddy.runtime.capabilities import RuntimeCapabilities
from artek_buddy.runtime.protocol import AgentRuntime
from artek_buddy.runtime.scripted import ScriptedRuntime
from artek_buddy.runtime.types import (
    AgentRuntimeCancelled,
    AgentRuntimeError,
    AgentRuntimeExhausted,
    AgentRuntimeTimeout,
    AgentRuntimeUnavailable,
)


def _make_settings(tmp_path) -> Settings:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        sandbox_provider="fake",
        cursor_api_key="",
        agent_data_dir=str(data_dir),
        agent_cwd=str(tmp_path),
    )


def _make_bot(bot_id: str, mode: str = "team") -> Bot:
    return Bot(
        id=bot_id,
        workspace_id="ws_default",
        name=f"Bot-{bot_id}",
        title="Assistant",
        description="",
        instructions="",
        color="#123456",
        notify_on_finish=True,
        pinned=False,
        archived_at=None,
        unread=False,
        parent_bot_id=None,
        thread_id=f"thr_{bot_id}",
        preview="",
        status="idle",
        computer_mode=mode,
        updated_at="2026-08-20T00:00:00Z",
        created_at="2026-08-20T00:00:00Z",
    )


# --- 1. AgentRuntime Protocol Conformance ---


def test_scripted_runtime_satisfies_agent_runtime_protocol(tmp_path) -> None:
    settings = _make_settings(tmp_path)
    runtime = ScriptedRuntime(settings)

    # Must satisfy runtime_checkable AgentRuntime Protocol
    assert isinstance(runtime, AgentRuntime)

    # Capability flags instead of isinstance
    assert isinstance(runtime.capabilities, RuntimeCapabilities)
    assert runtime.capabilities.streaming is True
    assert runtime.capabilities.cancellation is True
    assert runtime.capabilities.subagents is True
    assert runtime.capabilities.computer is True
    assert runtime.capabilities.memory is True
    assert runtime.capabilities.models_catalog is False

    # Lifecycle and control methods
    assert runtime.health() is True
    assert runtime.build_session_resume("bot_1") is None

    # Context & turn resolution
    ctx = runtime.resolve_turn_context("bot_1")
    assert isinstance(ctx, tuple) and len(ctx) == 3

    # Cancellation
    assert runtime.is_run_cancelled("run_test_1") is False
    runtime.cancel_run("run_test_1")
    assert runtime.is_run_cancelled("run_test_1") is True


@pytest.mark.asyncio
async def test_scripted_runtime_stream_conformance(tmp_path) -> None:
    settings = _make_settings(tmp_path)
    runtime = ScriptedRuntime(settings)
    await runtime.start()

    events = []
    async for event in runtime.stream("plain hello"):
        events.append(event)
    assert len(events) > 0


@pytest.mark.live
def test_cursor_runtime_satisfies_agent_runtime_protocol_if_live(tmp_path) -> None:
    key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not key:
        pytest.skip("CURSOR_API_KEY not set")

    from cursor_sdk import AsyncClient

    from artek_buddy.runtime.cursor import CursorRuntime

    client = MagicMock(spec=AsyncClient)
    settings = _make_settings(tmp_path)
    runtime = CursorRuntime(client, settings)

    assert isinstance(runtime, AgentRuntime)
    assert isinstance(runtime.capabilities, RuntimeCapabilities)
    assert runtime.capabilities.models_catalog is True
    assert runtime.health() is True


# --- 2. SupervisorGateway Protocol Conformance ---


def test_fake_supervisor_client_satisfies_supervisor_gateway() -> None:
    client = FakeSupervisorClient()
    assert isinstance(client, SupervisorGateway)

    # Capabilities
    assert isinstance(client.capabilities, ComputerCapabilities)
    assert client.capabilities.team_desktop is True
    assert client.capabilities.private_desktop is True
    assert client.capabilities.screen_preview is False  # Fake sandbox has no noVNC port
    assert client.capabilities.direct_execution is True

    # Health
    assert client.health() is True

    # Provision, inspect, execute, stop lifecycle
    box = client.provision("bot_team", "team-ws")
    assert box.running is True
    assert box.id.startswith("fake-")

    inspected = client.inspect(box.id)
    assert inspected.running is True

    res = client.execute(box.id, "echo hello")
    assert res.get("ok") is True
    assert res.get("exit_code") == 0

    client.stop(box.id)
    stopped = client.inspect(box.id)
    assert stopped.running is False


def test_real_supervisor_client_satisfies_supervisor_gateway() -> None:
    client = SupervisorClient("http://127.0.0.1:7091", "test-token")
    assert isinstance(client, SupervisorGateway)
    assert isinstance(client.capabilities, ComputerCapabilities)
    assert client.capabilities.screen_preview is True


# --- 3. ComputerGateway Protocol Conformance ---


def test_computer_service_satisfies_computer_gateway(tmp_path) -> None:
    settings = _make_settings(tmp_path)
    fake_client = FakeSupervisorClient()

    # Create mock HistoryStore for ComputerService
    mock_store = MagicMock()
    from artek_buddy.computer.models import ComputerRecord

    def fake_get_computer(bot: Bot) -> ComputerRecord:
        home = "team-ws" if bot.computer_mode == "team" else f"bot-{bot.id}"
        return ComputerRecord(
            id=f"comp_{bot.id}",
            workspace_id="ws_default",
            scope=bot.computer_mode,
            scope_key=home,
            home_key=home,
            home_revision=None,
            kind="fake",
            provider_ref=f"fake-{home}",
            state="running",
            control_holder="none",
            control_lease_id=None,
            control_lease_expires_at=None,
            control_bot_id=None,
            execution_run_id=None,
            execution_bot_id=None,
            execution_lease_expires_at=None,
            sleep_at=None,
            updated_at="2026-08-20T00:00:00Z",
        )

    mock_store.get_computer_for_bot = fake_get_computer
    mock_store.busy_bot_name.return_value = None

    service = ComputerService(mock_store, settings, client=fake_client)
    assert isinstance(service, ComputerGateway)

    # Capabilities match the client
    assert isinstance(service.capabilities, ComputerCapabilities)
    assert service.capabilities.team_desktop is True
    assert service.capabilities.private_desktop is True
    assert service.health() is True

    # Team vs Private handling
    team_bot = _make_bot("bot_team_1", mode="team")
    priv_bot = _make_bot("bot_priv_1", mode="dedicated")

    team_status = service.status(team_bot)
    assert team_status.mode == "team"

    priv_status = service.status(priv_bot)
    assert priv_status.mode == "dedicated"

    # Execution through supervisor boundary
    exec_res = service.execute(team_bot, "echo test")
    assert exec_res.get("ok") is True


# --- 4. Error Categories and Secret Redaction Conformance ---


def test_error_categories_and_transient_flags() -> None:
    # Unavailable (transient / retryable)
    err_unavail = AgentRuntimeUnavailable("Host unreachable")
    assert err_unavail.category == "unavailable"
    assert err_unavail.is_transient is True
    assert err_unavail.retryable is True

    comp_unavail = ComputerUnavailable("Proxy down")
    assert comp_unavail.category == "unavailable"
    assert comp_unavail.is_transient is True
    assert comp_unavail.retryable is True

    # Timeout (transient / retryable)
    err_timeout = AgentRuntimeTimeout("Request timed out")
    assert err_timeout.category == "timeout"
    assert err_timeout.is_transient is True
    assert err_timeout.retryable is True

    comp_timeout = ComputerTimeout("Docker call timed out")
    assert comp_timeout.category == "timeout"
    assert comp_timeout.is_transient is True
    assert comp_timeout.retryable is True

    # Cancelled (permanent / non-retryable)
    err_cancel = AgentRuntimeCancelled()
    assert err_cancel.category == "cancelled"
    assert err_cancel.is_transient is False
    assert err_cancel.retryable is False

    comp_cancel = ComputerCancelled()
    assert comp_cancel.category == "cancelled"
    assert comp_cancel.is_transient is False
    assert comp_cancel.retryable is False

    # Exhausted (capacity / busy)
    err_exhaust = AgentRuntimeExhausted("Rate limit exceeded")
    assert err_exhaust.category == "exhausted"
    assert err_exhaust.is_transient is False
    assert err_exhaust.retryable is True

    comp_busy = ComputerBusy("DeskBot")
    assert comp_busy.category == "exhausted"
    assert comp_busy.is_transient is False
    assert comp_busy.retryable is True

    # Standard / Permanent error
    err_perm = AgentRuntimeError("Invalid request parameter", category="permanent")
    assert err_perm.category == "permanent"
    assert err_perm.is_transient is False
    assert err_perm.retryable is False

    comp_perm = ComputerError("Invalid file path", category="permanent")
    assert comp_perm.category == "permanent"
    assert comp_perm.is_transient is False
    assert comp_perm.retryable is False


def test_error_safe_message_redacts_secrets() -> None:
    secret_token = "ci-host-token-aabbccddeeff001122334455"
    bearer_token = "Bearer test_secret_bearer_value_12345"
    pairing_code = "ABCD-EFGH"
    raw_message = (
        f"Failed call with {bearer_token} and token={secret_token} "
        f"to postgresql://user:password@127.0.0.1:5432/db "
        f"using code {pairing_code} and /novnc/sensitive_token_abc"
    )

    agent_err = AgentRuntimeError(raw_message)
    comp_err = ComputerError(raw_message)

    for err in (agent_err, comp_err):
        safe = err.safe_message
        assert "test_secret_bearer_value_12345" not in safe
        assert secret_token not in safe
        assert "password" not in safe
        assert pairing_code not in safe
        assert "sensitive_token_abc" not in safe
        assert "[redacted]" in safe
