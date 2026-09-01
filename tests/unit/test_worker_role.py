from types import SimpleNamespace

from artek_buddy.runtime.tools.product import ProductTools


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
