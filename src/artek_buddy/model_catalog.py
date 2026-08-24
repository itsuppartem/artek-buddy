from __future__ import annotations

from dataclasses import dataclass

import httpx

NEEDS_MODEL_TEXT = "Open Models. Paste an API key, pick a model, then send again."
PLACEHOLDER_KEYS = {"crsr_your_key_here"}


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    catalog_url: str
    complete_url: str
    style: str


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        "cursor",
        "Cursor",
        "",
        "",
        "cursor",
    ),
    Provider(
        "openrouter",
        "OpenRouter",
        "https://openrouter.ai/api/v1/models",
        "https://openrouter.ai/api/v1/chat/completions",
        "openai",
    ),
    Provider(
        "openai",
        "OpenAI",
        "https://api.openai.com/v1/models",
        "https://api.openai.com/v1/chat/completions",
        "openai",
    ),
    Provider(
        "anthropic",
        "Anthropic",
        "https://api.anthropic.com/v1/models",
        "https://api.anthropic.com/v1/messages",
        "anthropic",
    ),
    Provider(
        "xai",
        "xAI (Grok)",
        "https://api.x.ai/v1/models",
        "https://api.x.ai/v1/chat/completions",
        "openai",
    ),
)

PROVIDERS_BY_ID = {item.id: item for item in PROVIDERS}


def provider_label(provider: str) -> str:
    found = PROVIDERS_BY_ID.get(provider)
    return found.label if found else provider


def unknown_provider(provider: str) -> bool:
    return provider not in PROVIDERS_BY_ID


def last_four(key: str) -> str:
    text = (key or "").strip()
    return text[-4:] if text else ""


def is_placeholder_key(key: str) -> bool:
    text = (key or "").strip()
    return not text or text in PLACEHOLDER_KEYS


def refused_key_message() -> str:
    return "That key was refused. Check it and Save again."


def fetch_failed_message() -> str:
    return "Could not load models. Check the key and try again."


def _ids_from_payload(payload: object) -> list[str]:
    if isinstance(payload, dict):
        rows = payload.get("data")
        if rows is None:
            rows = payload.get("models")
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    ids: list[str] = []
    for item in rows or []:
        if isinstance(item, dict):
            model_id = item.get("id")
        else:
            model_id = item
        if model_id:
            ids.append(str(model_id))
    return ids


async def fetch_cursor_models(key: str, runtime: object | None = None) -> list[str]:
    """List Cursor models from the running bridge. There is no public catalog URL."""
    _ = key
    lister = getattr(runtime, "list_models", None)
    if lister is None:
        raise RuntimeError(fetch_failed_message())
    rows = await lister()
    ids: list[str] = []
    for item in rows or []:
        if isinstance(item, dict):
            if item.get("provider") not in (None, "cursor"):
                continue
            model_id = item.get("id")
        else:
            model_id = getattr(item, "id", None)
        if model_id:
            ids.append(str(model_id))
    if not ids:
        raise RuntimeError(fetch_failed_message())
    return ids


async def fetch_models(provider: str, key: str, *, scripted: bool = False) -> list[str]:
    if unknown_provider(provider):
        raise ValueError("unknown provider")
    if scripted:
        return ["scripted"]
    spec = PROVIDERS_BY_ID[provider]
    if spec.style == "cursor" or not spec.catalog_url:
        raise RuntimeError(fetch_failed_message())
    headers = {"Authorization": f"Bearer {key.strip()}"}
    if spec.style == "anthropic":
        headers = {
            "x-api-key": key.strip(),
            "anthropic-version": "2023-06-01",
        }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(spec.catalog_url, headers=headers)
    if response.status_code in {401, 403}:
        raise PermissionError(refused_key_message())
    if response.status_code >= 400:
        raise RuntimeError(fetch_failed_message())
    ids = _ids_from_payload(response.json())
    return ids


async def complete_chat(provider: str, key: str, model: str, prompt: str) -> str:
    spec = PROVIDERS_BY_ID[provider]
    if spec.style == "anthropic":
        headers = {
            "x-api-key": key.strip(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(spec.complete_url, headers=headers, json=body)
        if response.status_code in {401, 403}:
            raise RuntimeError(refused_key_message())
        if response.status_code >= 400:
            raise RuntimeError(fetch_failed_message())
        payload = response.json()
        parts = payload.get("content") or []
        texts = [
            str(item.get("text") or "")
            for item in parts
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        return "".join(texts).strip()
    headers = {
        "Authorization": f"Bearer {key.strip()}",
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(spec.complete_url, headers=headers, json=body)
    if response.status_code in {401, 403}:
        raise RuntimeError(refused_key_message())
    if response.status_code >= 400:
        raise RuntimeError(fetch_failed_message())
    payload = response.json()
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = (choices[0] or {}).get("message") or {}
    return str(message.get("content") or "").strip()
