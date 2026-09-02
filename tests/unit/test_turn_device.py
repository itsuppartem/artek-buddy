from __future__ import annotations

import threading
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


def test_overlapping_turns_keep_own_devices(tmp_path) -> None:
    runtime = RuntimeBase(_settings(tmp_path))
    lead = TurnContext(
        bot_id="bot_a",
        run_id="run_a",
        thread_id="th",
        role="lead",
        device_id="dev_a",
    )
    other = TurnContext(
        bot_id="bot_a",
        run_id="run_b",
        thread_id="th",
        role="lead",
        device_id="dev_b",
    )
    runtime.freeze_turn(lead)
    runtime.freeze_turn(other)
    runtime.set_turn_device("dev_b")
    seen: dict[str, str | None] = {}
    barrier = threading.Barrier(2)

    def run(label: str, ctx: TurnContext) -> None:
        barrier.wait()
        tokens = runtime.apply_callback_context(ctx)
        try:
            seen[label] = runtime.resolve_turn_device()
        finally:
            runtime.reset_callback_context(tokens)

    threads = [
        threading.Thread(target=run, args=("a", lead)),
        threading.Thread(target=run, args=("b", other)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert seen == {"a": "dev_a", "b": "dev_b"}
    assert not hasattr(runtime, "_last_device")


def test_follow_up_actor_does_not_steal_live_turn_device(tmp_path) -> None:
    runtime = RuntimeBase(_settings(tmp_path))
    live = TurnContext(
        bot_id="bot_a",
        run_id="run_live",
        thread_id="th",
        role="lead",
        device_id="dev_a",
    )
    runtime.freeze_turn(live)
    runtime.set_turn_device("dev_b")
    tokens = runtime.apply_callback_context(live)
    try:
        assert runtime.resolve_turn_device() == "dev_a"
        assert runtime.resolve_turn().device_id == "dev_a"
    finally:
        runtime.reset_callback_context(tokens)


def test_consent_gate_uses_frozen_device_not_later_actor(tmp_path) -> None:
    seen: list[str | None] = []

    class Hub:
        def require(self, **kwargs: object) -> tuple[bool, None]:
            seen.append(kwargs.get("device_id"))  # type: ignore[arg-type]
            return True, None

    runtime = RuntimeBase(_settings(tmp_path))
    runtime.consent = Hub()
    live = TurnContext(
        bot_id="bot_a",
        run_id="run_live",
        thread_id="th",
        role="lead",
        device_id="dev_a",
    )
    runtime.freeze_turn(live)
    runtime.set_turn_device("dev_b")
    tools = ProductTools(runtime)
    tokens = runtime.apply_callback_context(live)
    try:
        allowed, _request = tools._consent_gate(
            "bot_a",
            "browse",
            "https://example.com",
            "Open https://example.com?",
        )
    finally:
        runtime.reset_callback_context(tokens)
    assert allowed is True
    assert seen == ["dev_a"]


def test_worker_inherits_parent_turn_device(tmp_path) -> None:
    runtime = RuntimeBase(_settings(tmp_path))
    runtime.store = SimpleNamespace(
        get_subagent=lambda run_id: (
            SimpleNamespace(parent_run_id="run_lead") if run_id == "sub_1" else None
        )
    )
    runtime.freeze_turn(
        TurnContext(
            bot_id="bot_a",
            run_id="run_lead",
            thread_id="th",
            role="lead",
            device_id="dev_a",
        )
    )
    runtime.set_current_turn_context(
        "bot_a",
        "sub_1",
        "th",
        agent_id="ag_worker",
        role="subagent",
    )
    found = runtime.resolve_turn("bot_a", agent_id="ag_worker")
    assert found is not None
    assert found.device_id == "dev_a"
    assert found.role == "subagent"


def test_stale_contextvar_does_not_impersonate_another_bot(tmp_path) -> None:
    leaked = RuntimeBase(_settings(tmp_path))
    leaked.set_current_turn_context(
        "bot_a",
        "run_host",
        "th",
        device_id="dev_a",
        role="lead",
    )
    live = RuntimeBase(_settings(tmp_path))
    live.freeze_turn(
        TurnContext(
            bot_id="bot_b",
            run_id="run_live",
            thread_id="th2",
            role="lead",
            device_id="dev_b",
        )
    )
    found = live.resolve_turn("bot_b")
    assert found is not None
    assert found.run_id == "run_live"
    assert found.device_id == "dev_b"


def test_host_actor_freezes_as_no_device(tmp_path) -> None:
    runtime = RuntimeBase(_settings(tmp_path))
    runtime.set_current_turn_context(
        "bot_a",
        "run_host",
        "th",
        device_id="host",
        role="lead",
    )
    found = runtime.resolve_turn("bot_a")
    assert found is not None
    assert found.device_id is None
    tokens = runtime.apply_callback_context(found)
    try:
        assert runtime.resolve_turn_device() is None
    finally:
        runtime.reset_callback_context(tokens)
