from types import SimpleNamespace
from unittest.mock import MagicMock

from artek_buddy.config import Settings
from artek_buddy.runtime.cursor import CursorRuntime, build_model


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
