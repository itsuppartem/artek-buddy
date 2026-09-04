from types import SimpleNamespace

from artek_buddy.bot_credentials import BotCredentialStatus, CredentialExecutionResult
from artek_buddy.config import Settings
from artek_buddy.runtime.base import RuntimeBase
from artek_buddy.runtime.tools.product import ProductTools
from artek_buddy.runtime.types import TurnContext


def _runtime(tmp_path) -> RuntimeBase:
    return RuntimeBase(
        Settings(
            agent_http_token="ci-host-token-aabbccddeeff001122334455",
            agent_runtime="scripted",
            sandbox_provider="fake",
            agent_data_dir=str(tmp_path / "data"),
            agent_cwd=str(tmp_path / "cwd"),
            cursor_api_key="",
        )
    )


def _message_tools(tmp_path):
    runtime = _runtime(tmp_path)
    bot = SimpleNamespace(id="bot_a")
    appended: list[str] = []

    def append_message(_bot, _blocks, run_id):
        appended.append(run_id)
        return SimpleNamespace(id=f"msg_{run_id}")

    runtime.store = SimpleNamespace(
        get_bot=lambda bot_id: bot if bot_id == bot.id else None,
        append_bot_message=append_message,
    )
    turn = TurnContext(bot_id=bot.id, run_id="run_message", thread_id="th", role="lead")
    runtime.freeze_turn(turn)
    return runtime, ProductTools(runtime), bot, turn, appended


def test_lead_cannot_use_worker_only_tools() -> None:
    tools = ProductTools(SimpleNamespace(store=None, settings=None))
    lead_specs = tools.specs("lead")
    lead = {spec.name for spec in lead_specs}
    worker = {spec.name for spec in tools.specs("subagent")}
    assert "spawn_subagent" in lead
    assert "send_message" in lead
    assert "run_owner_command" not in lead
    assert "browser_act" not in lead
    assert "send_message" not in worker
    assert "run_owner_command" in worker
    assert "run_credential_scoped_command" in worker
    assert "run_credential_scoped_command" not in lead
    assert "report_progress" in worker
    assert "report_progress" not in lead
    assert "spawn_subagent" not in worker


def test_send_message_spec_distinguishes_terminal_from_interim() -> None:
    tools = ProductTools(SimpleNamespace(store=None, settings=None))
    send = next(spec for spec in tools.specs("lead") if spec.name == "send_message")
    terminal = send.input_schema["properties"]["terminal"]
    assert terminal["type"] == "boolean"
    assert send.input_schema["required"] == ["text", "terminal"]
    assert "default" not in terminal
    assert "terminal=true" in send.description
    assert "interim" in send.description


def test_terminal_send_message_marks_only_its_run_and_instructs_the_lead(tmp_path) -> None:
    runtime, tools, bot, terminal, appended = _message_tools(tmp_path)
    interim = TurnContext(bot_id=bot.id, run_id="run_interim", thread_id="th", role="lead")
    runtime.freeze_turn(interim)

    result = tools.execute(
        "send_message",
        {"text": "The complete answer.", "terminal": True},
        bound_bot_id=bot.id,
        turn=terminal,
    )

    assert result["ok"] is True
    assert result["terminal"] is True
    assert "Do not repeat or paraphrase" in result["owner_instruction"]
    assert runtime.has_sent_terminal_message_in_turn(terminal.run_id) is True
    assert runtime.has_sent_terminal_message_in_turn(interim.run_id) is False
    assert appended == [terminal.run_id]
    runtime.clear_active_turn(run_id=terminal.run_id)
    assert runtime.has_sent_terminal_message_in_turn(terminal.run_id) is False


def test_send_message_rejects_missing_or_malformed_terminal_choice(tmp_path) -> None:
    runtime, tools, bot, turn, appended = _message_tools(tmp_path)

    missing = tools.execute(
        "send_message",
        {"text": "A full answer without a choice."},
        bound_bot_id=bot.id,
        turn=turn,
    )
    malformed = tools.execute(
        "send_message",
        {"text": "A full answer with a malformed choice.", "terminal": "true"},
        bound_bot_id=bot.id,
        turn=turn,
    )

    assert missing == {"ok": False, "error": "terminal is required and must be a boolean"}
    assert malformed == {"ok": False, "error": "terminal is required and must be a boolean"}
    assert appended == []
    assert runtime.has_sent_message_in_turn(turn.run_id) is False


def test_send_message_rejects_terminal_owner_question(tmp_path) -> None:
    runtime, tools, bot, turn, appended = _message_tools(tmp_path)

    result = tools.execute(
        "send_message",
        {"text": "Which city?", "options": ["Belgrade", "Novi Sad"], "terminal": True},
        bound_bot_id=bot.id,
        turn=turn,
    )

    assert result == {
        "ok": False,
        "error": "send_message with options cannot be terminal",
    }
    assert appended == []
    assert runtime.has_sent_terminal_message_in_turn(turn.run_id) is False


def test_lead_and_worker_get_connected_app_tools() -> None:
    store = SimpleNamespace(
        raw_connection_key=lambda: "ak-test",
        connected_slugs=lambda: ["docs"],
    )
    settings = SimpleNamespace(agent_runtime="scripted")
    tools = ProductTools(SimpleNamespace(store=store, settings=settings))
    lead = {spec.name for spec in tools.specs("lead")}
    worker = {spec.name for spec in tools.specs("subagent")}
    assert "docs_read" in lead
    assert "docs_read" in worker
    assert "run_owner_command" not in lead
    assert "run_owner_command" in worker


def test_lead_execute_refuses_this_pc_ssh(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    tools = ProductTools(runtime)
    lead = TurnContext(bot_id="bot_a", run_id="run_lead", thread_id="th", role="lead")
    worker = TurnContext(bot_id="bot_a", run_id="sub_1", thread_id="th", role="subagent")
    refused = tools.execute(
        "run_owner_command",
        {"command": "sleep 120"},
        bound_bot_id="bot_a",
        turn=lead,
    )
    assert refused["ok"] is False
    assert "spawn_subagent" in str(refused.get("error"))
    assert "run_owner_command" in str(refused.get("error"))
    allowed = tools.execute(
        "run_owner_command",
        {"command": "ls"},
        bound_bot_id="bot_a",
        turn=worker,
    )
    assert "lead cannot use" not in str(allowed.get("error"))
    assert "spawn_subagent" not in str(allowed.get("error"))


def test_lead_execute_refuses_report_progress(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    tools = ProductTools(runtime)
    lead = TurnContext(bot_id="bot_a", run_id="run_lead", thread_id="th", role="lead")
    refused = tools.execute(
        "report_progress",
        {"step": "commit"},
        bound_bot_id="bot_a",
        turn=lead,
    )
    assert refused["ok"] is False
    assert "report_progress" in str(refused.get("error"))


def test_credential_scoped_tool_binds_current_bot_and_home() -> None:
    calls: list[tuple[str, str, str, str, float]] = []

    class Credentials:
        def list_for_bot(self, _bot_id):
            return [
                BotCredentialStatus(
                    provider="github",
                    scope="this_bot",
                    last_four="1234",
                    updated_at="2026-09-04T00:00:00Z",
                )
            ]

        def execute(
            self,
            bot_id,
            home_key,
            command,
            *,
            cwd=".",
            timeout_seconds=30,
            credential_snapshot=None,
        ):
            assert credential_snapshot
            calls.append((bot_id, home_key, command, cwd, timeout_seconds))
            return CredentialExecutionResult(
                ok=True,
                exit_code=0,
                stdout="published\n",
                stderr="",
            )

    bot = SimpleNamespace(id="bot_" + ("a" * 16))
    runtime = SimpleNamespace(
        credential_store=Credentials(),
        store=SimpleNamespace(
            get_bot=lambda bot_id: bot if bot_id == bot.id else None,
            get_computer_for_bot=lambda _bot: SimpleNamespace(home_key="team-ws"),
        ),
        resolve_turn_context=lambda _bot: (bot.id, "sub_1", "thr_1"),
    )
    result = ProductTools(runtime)._exec_run_credential_scoped_command(
        {"command": "python -m build", "cwd": "repo", "timeout_seconds": 12},
        bot.id,
    )
    assert result["ok"] is True
    assert result["stdout"] == "published\n"
    assert calls == [(bot.id, "team-ws", "python -m build", "repo", 12.0)]


def test_lead_execute_rejects_credential_command_before_handler(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    called: list[str] = []
    runtime.credential_store = SimpleNamespace(
        execute=lambda *_args, **_kwargs: called.append("execute")
    )
    tools = ProductTools(runtime)
    lead = TurnContext(bot_id="bot_a", run_id="run_lead", thread_id="th", role="lead")
    refused = tools.execute(
        "run_credential_scoped_command",
        {"command": "gh auth status"},
        bound_bot_id="bot_a",
        turn=lead,
    )
    assert refused == {
        "ok": False,
        "error": (
            "lead cannot use run_credential_scoped_command; "
            "spawn_subagent for credential-scoped work"
        ),
    }
    assert called == []


def test_credential_command_consent_has_metadata_but_no_value() -> None:
    secret = "ghp_" + ("S" * 36)
    captured: list[dict] = []
    executed: list[str] = []

    class Consent:
        def require(self, **kwargs):
            captured.append(kwargs)
            return False, "cns_1"

    class Credentials:
        def list_for_bot(self, _bot_id):
            return [
                BotCredentialStatus(
                    provider="github",
                    scope="this_bot",
                    last_four="SSSS",
                    updated_at="2026-09-04T00:00:00Z",
                    env_name="GH_TOKEN",
                )
            ]

        def execute(self, *_args, **_kwargs):
            executed.append("execute")
            raise AssertionError("denied command must not execute")

    bot = SimpleNamespace(id="bot_" + ("a" * 16))
    runtime = SimpleNamespace(
        consent=Consent(),
        credential_store=Credentials(),
        store=SimpleNamespace(
            get_bot=lambda _bot_id: bot,
            get_computer_for_bot=lambda _bot: SimpleNamespace(home_key="team-ws"),
        ),
        resolve_turn_context=lambda _bot: (bot.id, "sub_1", "thr_1"),
        resolve_turn_device=lambda: "dev_1",
    )
    result = ProductTools(runtime)._exec_run_credential_scoped_command(
        {"command": "gh auth status", "cwd": "repo"},
        bot.id,
    )
    assert result == {"ok": False, "error": "denied by owner", "denied": True}
    assert executed == []
    packed = str(captured)
    assert "GitHub" in packed
    assert "SSSS" in packed
    assert "gh auth status" in packed
    assert "repo" in packed
    assert secret not in packed


def test_credential_command_reasks_when_metadata_changes_during_consent() -> None:
    calls = 0
    executed: list[str] = []

    class Consent:
        def require(self, **_kwargs):
            return True, "cns_1"

    class Credentials:
        def list_for_bot(self, _bot_id):
            nonlocal calls
            calls += 1
            return [
                BotCredentialStatus(
                    provider="github",
                    scope="this_bot",
                    last_four="AAAA" if calls == 1 else "BBBB",
                    updated_at=f"2026-09-04T00:00:0{calls}Z",
                    env_name="GH_TOKEN",
                )
            ]

        def execute(self, *_args, **_kwargs):
            executed.append("execute")
            raise AssertionError("changed credentials need fresh consent")

    bot = SimpleNamespace(id="bot_" + ("a" * 16))
    runtime = SimpleNamespace(
        consent=Consent(),
        credential_store=Credentials(),
        store=SimpleNamespace(
            get_bot=lambda _bot_id: bot,
            get_computer_for_bot=lambda _bot: SimpleNamespace(home_key="team-ws"),
        ),
        resolve_turn_context=lambda _bot: (bot.id, "sub_1", "thr_1"),
        resolve_turn_device=lambda: "dev_1",
    )
    result = ProductTools(runtime)._exec_run_credential_scoped_command(
        {"command": "gh auth status"},
        bot.id,
    )
    assert result == {
        "ok": False,
        "error": "saved credentials changed; run the command again for fresh approval",
    }
    assert executed == []


def test_cancelled_turn_refuses_further_tools(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    tools = ProductTools(runtime)
    lead = TurnContext(bot_id="bot_a", run_id="run_lead", thread_id="th", role="lead")
    runtime.mark_runs_cancelled(["run_lead"])
    result = tools.execute("list_subagents", {}, bound_bot_id="bot_a", turn=lead)
    assert result["ok"] is False
    assert result.get("error") == "turn was cancelled"
