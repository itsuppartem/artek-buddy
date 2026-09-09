from __future__ import annotations

import pytest

from artek_buddy.model_catalog import (
    NEEDS_MODEL_TEXT,
    PROVIDERS,
    catalog_entry,
    complete_chat,
    fetch_cursor_models,
    fetch_failed_message,
    fetch_models,
    is_placeholder_key,
    last_four,
    preferred_model,
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
    assert preferred_model(["composer-2", "grok-4.6", "gpt-5.4"]) == "grok-4.6"
    assert preferred_model(["scripted"]) == "scripted"
    assert preferred_model([]) is None


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

    assert await fetch_cursor_models("crsr_live", _Runtime()) == [
        {"id": "grok-4.6"},
        {"id": "composer-2"},
    ]

    class _Mixed:
        async def list_models(self) -> list[dict[str, str]]:
            return [
                {"id": "scripted", "provider": "openrouter"},
                {"id": "grok-4.6", "provider": "cursor"},
            ]

    assert await fetch_cursor_models("crsr_live", _Mixed()) == [{"id": "grok-4.6"}]
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


def test_catalog_entry_keeps_variants_and_parameters() -> None:
    class _Value:
        value = "xhigh"
        display_name = "Extra high"

    class _Param:
        id = "effort"
        values = [_Value()]

    class _Variant:
        display_name = "fast"

    class _Model:
        id = "grok-4.6"
        variants = [_Variant()]
        parameters = [_Param()]

    assert catalog_entry(_Model()) == {
        "id": "grok-4.6",
        "variants": ["fast"],
        "parameters": [
            {"id": "effort", "values": [{"value": "xhigh", "display_name": "Extra high"}]}
        ],
    }
    assert catalog_entry({"id": "grok-4.6"}) == {"id": "grok-4.6"}
    assert catalog_entry("scripted") == {"id": "scripted"}
    assert preferred_model([{"id": "composer-2"}, {"id": "grok-4.6"}]) == "grok-4.6"


@pytest.mark.asyncio
async def test_cursor_catalog_keeps_runtime_extras() -> None:
    class _Runtime:
        async def list_models(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "grok-4.6",
                    "variants": ["fast"],
                    "parameters": [
                        {
                            "id": "effort",
                            "values": [{"value": "xhigh", "display_name": "Extra high"}],
                        }
                    ],
                }
            ]

    assert await fetch_cursor_models("crsr_live", _Runtime()) == [
        {
            "id": "grok-4.6",
            "variants": ["fast"],
            "parameters": [
                {"id": "effort", "values": [{"value": "xhigh", "display_name": "Extra high"}]}
            ],
        }
    ]
