from __future__ import annotations

import pytest

from artek_buddy.model_catalog import (
    NEEDS_MODEL_TEXT,
    PROVIDERS,
    complete_chat,
    fetch_cursor_models,
    fetch_failed_message,
    fetch_models,
    is_placeholder_key,
    last_four,
    provider_label,
    refused_key_message,
    unknown_provider,
)


def test_provider_labels_and_last_four() -> None:
    assert [item.id for item in PROVIDERS] == [
        "cursor",
        "openrouter",
        "openai",
        "anthropic",
        "xai",
    ]
    assert provider_label("xai") == "xAI (Grok)"
    assert last_four("sk-test-secret-wxyz") == "wxyz"
    assert last_four("ab") == "ab"
    assert is_placeholder_key("")
    assert is_placeholder_key("crsr_your_key_here")
    assert not is_placeholder_key("crsr_live")
    assert unknown_provider("nope")
    assert "Open Models" in NEEDS_MODEL_TEXT


@pytest.mark.asyncio
async def test_scripted_catalog_is_canned() -> None:
    models = await fetch_models("openrouter", "test-secret-xxxx", scripted=True)
    assert models == ["scripted"]
    assert await fetch_models("cursor", "crsr_live", scripted=True) == ["scripted"]


@pytest.mark.asyncio
async def test_cursor_catalog_comes_from_the_running_runtime() -> None:
    class _Runtime:
        async def list_models(self) -> list[dict[str, str]]:
            return [{"id": "grok-4.6"}, {"id": "composer-2"}]

    assert await fetch_cursor_models("crsr_live", _Runtime()) == ["grok-4.6", "composer-2"]

    class _Mixed:
        async def list_models(self) -> list[dict[str, str]]:
            return [
                {"id": "scripted", "provider": "openrouter"},
                {"id": "grok-4.6", "provider": "cursor"},
            ]

    assert await fetch_cursor_models("crsr_live", _Mixed()) == ["grok-4.6"]
    with pytest.raises(RuntimeError, match="Could not load models"):
        await fetch_cursor_models("crsr_live", None)
    with pytest.raises(RuntimeError, match="Could not load models"):
        await fetch_models("cursor", "crsr_live", scripted=False)
    assert "Could not load" in fetch_failed_message()


class _Resp:
    def __init__(self, status: int, payload: object) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> object:
        return self._payload


class _Client:
    def __init__(self, response: _Resp) -> None:
        self._response = response

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, *args: object, **kwargs: object) -> _Resp:
        return self._response

    async def post(self, *args: object, **kwargs: object) -> _Resp:
        return self._response


@pytest.mark.asyncio
async def test_fetch_and_complete_openai_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: _Client(_Resp(200, {"data": [{"id": "gpt-test"}]})),
    )
    assert await fetch_models("openai", "sk-test", scripted=False) == ["gpt-test"]
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: _Client(_Resp(200, {"choices": [{"message": {"content": "pong"}}]})),
    )
    assert await complete_chat("openai", "sk-test", "gpt-test", "hello") == "pong"


@pytest.mark.asyncio
async def test_fetch_refused_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _Client(_Resp(401, {})))
    with pytest.raises(PermissionError, match="refused"):
        await fetch_models("openai", "bad", scripted=False)
    assert "refused" in refused_key_message()
