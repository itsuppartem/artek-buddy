from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from artek_buddy.config import Settings
from artek_buddy.runtime.cursor import CURSOR_DISALLOWED_BUILTIN, CursorRuntime, build_model
from artek_buddy.runtime.cursor_wait import send_local_options


def _settings(*, fast: bool) -> Settings:
    return Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        agent_runtime="cursor",
        cursor_model_fast=fast,
        sandbox_provider="fake",
    )


def _params(selection) -> dict[str, str]:
    return {str(item.id): str(item.value) for item in (selection.params or [])}


def test_build_model_sends_fast_false_when_the_store_says_false() -> None:
    settings = _settings(fast=True)
    off = build_model(settings, "grok-4.6", effort="low", fast=False)
    on = build_model(settings, "grok-4.6", effort="low", fast=True)
    fallback = build_model(settings, "grok-4.6", effort="low", fast=None)
    assert _params(off)["fast"] == "false"
    assert _params(on)["fast"] == "true"
    assert _params(fallback)["fast"] == "true"


def test_model_selection_sends_store_fast_off_for_lead_and_workers() -> None:
    store = SimpleNamespace(
        get_default_model=lambda: ("cursor", "grok-4.6"),
        get_model_params=lambda: ("xhigh", False),
    )
    runtime = CursorRuntime(
        client=MagicMock(),
        settings=_settings(fast=True),
        store=store,
    )
    params = _params(runtime.model)
    assert runtime.model.id == "grok-4.6"
    assert params["effort"] == "xhigh"
    assert params["fast"] == "false"


def test_build_model_omits_effort_on_composer_when_fast_is_off() -> None:
    settings = _settings(fast=True)
    off = build_model(settings, "composer-2.5", effort="xhigh", fast=False)
    grok = build_model(settings, "grok-4.6", effort="xhigh", fast=False)
    assert _params(off) == {"fast": "false"}
    assert _params(grok)["effort"] == "xhigh"
    assert _params(grok)["fast"] == "false"


def test_model_selection_omits_effort_for_composer() -> None:
    store = SimpleNamespace(
        get_default_model=lambda: ("cursor", "composer-2.5"),
        get_model_params=lambda: ("xhigh", False),
    )
    runtime = CursorRuntime(
        client=MagicMock(),
        settings=_settings(fast=True),
        store=store,
    )
    params = _params(runtime.model)
    assert runtime.model.id == "composer-2.5"
    assert "effort" not in params
    assert params["fast"] == "false"


def test_send_options_repeat_fast_off_on_every_send() -> None:
    model = build_model(_settings(fast=True), "composer-2.5", effort="xhigh", fast=False)
    payload = send_local_options("/data/homes/bot", model=model)
    forced = send_local_options("/data/homes/bot", force=True, model=model)
    assert payload["local"] == {"cwd": "/data/homes/bot"}
    assert forced["local"]["force"] is True
    assert payload["model"]["id"] == "composer-2.5"
    assert payload["model"]["params"] == [{"id": "fast", "value": "false"}]
    assert forced["model"] == payload["model"]


@pytest.mark.asyncio
async def test_create_and_resume_deny_builtin_task(tmp_path) -> None:
    created: dict[str, Any] = {}
    resumed: dict[str, Any] = {}

    class _Agents:
        async def create(self, options: Any = None, **_kwargs: Any) -> Any:
            created["options"] = options
            return SimpleNamespace(agent_id="ag-new")

        async def resume(self, agent_id: str, options: Any = None) -> Any:
            resumed["id"] = agent_id
            resumed["options"] = options
            return SimpleNamespace(agent_id=agent_id)

    store = SimpleNamespace(
        get_default_model=lambda: ("cursor", "composer-2.5"),
        get_model_params=lambda: ("xhigh", False),
        get_bot=lambda _bot_id: None,
        raw_connection_key=lambda: None,
    )
    runtime = CursorRuntime(
        client=SimpleNamespace(agents=_Agents()),
        settings=Settings(
            agent_http_token="ci-host-token-aabbccddeeff001122334455",
            agent_runtime="cursor",
            cursor_model_fast=True,
            sandbox_provider="fake",
            agent_cwd=str(tmp_path / "workspace"),
            agent_data_dir=str(tmp_path / "data"),
        ),
        store=store,
    )
    live = await runtime.create_session(name="horse", persist_default=False, bot_id="bot-1")
    assert live == "ag-new"
    created_opts = created["options"]
    assert list(created_opts.disallowed_tools) == list(CURSOR_DISALLOWED_BUILTIN)
    assert _params(created_opts.model)["fast"] == "false"
    assert "effort" not in _params(created_opts.model)

    runtime._agents.clear()
    resumed_id = await runtime.ensure_session("ag-old", name="horse", bot_id="bot-1")
    assert resumed_id == "ag-old"
    resumed_opts = resumed["options"]
    assert list(resumed_opts.disallowed_tools) == list(CURSOR_DISALLOWED_BUILTIN)
    assert _params(resumed_opts.model)["fast"] == "false"
