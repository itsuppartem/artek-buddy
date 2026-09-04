from artek_buddy.config import Settings
from artek_buddy.runtime.cursor import build_model


def _settings(*, fast: bool) -> Settings:
    return Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        agent_runtime="cursor",
        cursor_model_fast=fast,
        sandbox_provider="fake",
    )


def _param_ids(selection) -> list[str]:
    return [str(getattr(item, "id", "")) for item in (selection.params or [])]


def test_build_model_omits_fast_when_the_store_says_false() -> None:
    settings = _settings(fast=True)
    off = build_model(settings, "grok-4.6", effort="low", fast=False)
    on = build_model(settings, "grok-4.6", effort="low", fast=True)
    fallback = build_model(settings, "grok-4.6", effort="low", fast=None)
    assert "fast" not in _param_ids(off)
    assert "fast" in _param_ids(on)
    assert "fast" in _param_ids(fallback)
