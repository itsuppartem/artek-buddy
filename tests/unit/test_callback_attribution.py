from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from artek_buddy.config import Settings
from artek_buddy.runtime.base import RuntimeBase
from artek_buddy.runtime.tools.product import ProductTools
from artek_buddy.runtime.types import TurnContext


def _settings(tmp_path) -> Settings:
    return Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        agent_runtime="scripted",
        sandbox_provider="fake",
        agent_data_dir=str(tmp_path / "data"),
        agent_cwd=str(tmp_path / "cwd"),
        cursor_api_key="",
    )


def test_ambiguous_same_bot_turns_fail_closed(tmp_path) -> None:
    runtime = RuntimeBase(_settings(tmp_path))
    runtime.freeze_turn(TurnContext(bot_id="bot_a", run_id="run_lead", thread_id="th", role="lead"))
    runtime.freeze_turn(
        TurnContext(bot_id="bot_a", run_id="sub_1", thread_id="th", role="subagent")
    )
    assert runtime.resolve_turn("bot_a") is None
    assert runtime.resolve_turn_context("bot_a") == (None, None, None)
    assert not hasattr(runtime, "_last_turn")
    assert not hasattr(runtime, "_last_role")


def test_unique_worker_turn_is_used_when_lead_is_idle(tmp_path) -> None:
    runtime = RuntimeBase(_settings(tmp_path))
    runtime.freeze_turn(
        TurnContext(bot_id="bot_a", run_id="sub_1", thread_id="th", role="subagent")
    )
    found = runtime.resolve_turn("bot_a")
    assert found is not None
    assert found.run_id == "sub_1"
    assert found.role == "subagent"


def test_threaded_callbacks_keep_frozen_run_and_role(tmp_path) -> None:
    runtime = RuntimeBase(_settings(tmp_path))
    lead = TurnContext(
        bot_id="bot_a",
        run_id="run_lead",
        thread_id="th",
        role="lead",
        agent_id="ag_lead",
    )
    worker = TurnContext(
        bot_id="bot_a",
        run_id="sub_1",
        thread_id="th",
        role="subagent",
        agent_id="ag_worker",
    )
    runtime.freeze_turn(lead)
    runtime.freeze_turn(worker)
    barrier = threading.Barrier(2)
    seen: dict[str, tuple[str, str, str]] = {}

    def run(label: str, ctx: TurnContext) -> None:
        barrier.wait()
        tokens = runtime.apply_callback_context(ctx)
        try:
            first = runtime.resolve_turn_context()
            role = runtime.resolve_turn_role()
            time.sleep(0.05)
            second = runtime.resolve_turn_context()
            seen[label] = (str(first[1]), role, str(second[1]))
        finally:
            runtime.reset_callback_context(tokens)

    threads = [
        threading.Thread(target=run, args=("lead", lead)),
        threading.Thread(target=run, args=("worker", worker)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert seen["lead"] == ("run_lead", "lead", "run_lead")
    assert seen["worker"] == ("sub_1", "subagent", "sub_1")


def test_worker_callback_does_not_drain_owner_inbox(tmp_path) -> None:
    runtime = RuntimeBase(_settings(tmp_path))
    store = SimpleNamespace(
        drained=[],
        clarifications=[],
        get_bot=lambda bot_id: SimpleNamespace(id=bot_id),
        drain_inbox=lambda bot_id: store.drained.append(bot_id) or [{"text": "owner ping"}],
        take_new_clarifications=lambda run_id: store.clarifications.append(run_id) or "use path B",
    )
    runtime.store = store
    runtime.subagents = SimpleNamespace(list_for=lambda bot: [])
    tools = ProductTools(runtime)
    lead = TurnContext(bot_id="bot_a", run_id="run_lead", thread_id="th", role="lead")
    worker = TurnContext(bot_id="bot_a", run_id="sub_1", thread_id="th", role="subagent")
    runtime.freeze_turn(lead)
    runtime.freeze_turn(worker)
    barrier = threading.Barrier(2)
    results: dict[str, dict] = {}

    def call(label: str, ctx: TurnContext) -> None:
        barrier.wait()
        results[label] = tools.execute("list_subagents", {}, bound_bot_id="bot_a", turn=ctx)

    threads = [
        threading.Thread(target=call, args=("lead", lead)),
        threading.Thread(target=call, args=("worker", worker)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results["lead"]["ok"] is True
    assert results["worker"]["ok"] is True
    assert store.drained == ["bot_a"]
    assert store.clarifications == ["sub_1"]
