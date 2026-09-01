from types import SimpleNamespace

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


def test_lead_cannot_use_worker_only_tools() -> None:
    tools = ProductTools(SimpleNamespace(store=None, settings=None))
    lead = {spec.name for spec in tools.specs("lead")}
    worker = {spec.name for spec in tools.specs("subagent")}
    assert "spawn_subagent" in lead
    assert "send_message" in lead
    assert "run_owner_command" not in lead
    assert "browser_act" not in lead
    assert "send_message" not in worker
    assert "run_owner_command" in worker
    assert "spawn_subagent" not in worker


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


def test_cancelled_turn_refuses_further_tools(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    tools = ProductTools(runtime)
    lead = TurnContext(bot_id="bot_a", run_id="run_lead", thread_id="th", role="lead")
    runtime.mark_runs_cancelled(["run_lead"])
    result = tools.execute("list_subagents", {}, bound_bot_id="bot_a", turn=lead)
    assert result["ok"] is False
    assert result.get("error") == "turn was cancelled"
