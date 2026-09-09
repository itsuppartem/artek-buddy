from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


def preferred_model(models: list[Any], want: str = "grok-4.6") -> str | None:
    names = catalog_model_ids(models)
    if want in names:
        return want
    return names[0] if names else None


def catalog_model_ids(models: list[Any]) -> list[str]:
    ids: list[str] = []
    for item in models:
        entry = catalog_entry(item)
        if entry is not None:
            ids.append(str(entry["id"]))
    return ids


def catalog_entry(item: Any) -> dict[str, Any] | None:
    """Normalize a catalog row from a string, mapping, or runtime model object."""
    if item is None:
        return None
    if isinstance(item, str):
        model_id = item.strip()
        return {"id": model_id} if model_id else None
    if isinstance(item, dict):
        model_id = item.get("id")
        if not model_id:
            return None
        row: dict[str, Any] = {"id": str(model_id)}
        provider = item.get("provider")
        if provider:
            row["provider"] = str(provider)
        variants = _variant_labels(item.get("variants"))
        if variants:
            row["variants"] = variants
        parameters = _parameter_rows(item.get("parameters"))
        if parameters:
            row["parameters"] = parameters
        return row
    model_id = getattr(item, "id", None)
    if not model_id:
        return None
    row = {"id": str(model_id)}
    variants = _variant_labels(getattr(item, "variants", None))
    if variants:
        row["variants"] = variants
    parameters = _parameter_rows(getattr(item, "parameters", None))
    if parameters:
        row["parameters"] = parameters
    return row


def catalog_extras(entry: dict[str, Any]) -> dict[str, Any]:
    extras: dict[str, Any] = {}
    variants = entry.get("variants")
    if variants:
        extras["variants"] = list(variants)
    parameters = entry.get("parameters")
    if parameters:
        extras["parameters"] = list(parameters)
    return extras


def _variant_labels(raw: Any) -> list[str]:
    labels: list[str] = []
    for item in raw or ():
        if isinstance(item, str):
            text = item.strip()
            if text:
                labels.append(text)
            continue
        if isinstance(item, dict):
            text = str(item.get("id") or item.get("display_name") or "").strip()
            if text:
                labels.append(text)
            continue
        text = str(getattr(item, "id", None) or getattr(item, "display_name", None) or "").strip()
        if text:
            labels.append(text)
    return labels


def _parameter_rows(raw: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in raw or ():
        if isinstance(item, dict):
            param_id = str(item.get("id") or "").strip()
            values_raw = item.get("values") or ()
        else:
            param_id = str(getattr(item, "id", "") or "").strip()
            values_raw = getattr(item, "values", None) or ()
        if not param_id:
            continue
        values: list[dict[str, str]] = []
        for value in values_raw:
            if isinstance(value, dict):
                text = str(value.get("value") or "").strip()
                name = str(value.get("display_name") or "").strip()
            else:
                text = str(getattr(value, "value", "") or "").strip()
                name = str(getattr(value, "display_name", "") or "").strip()
            if not text:
                continue
            row = {"value": text}
            if name:
                row["display_name"] = name
            values.append(row)
        rows.append({"id": param_id, "values": values})
    return rows


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


async def fetch_cursor_models(key: str, runtime: object | None = None) -> list[dict[str, Any]]:
    """List Cursor models from the running bridge. There is no public catalog URL."""
    _ = key
    lister = getattr(runtime, "list_models", None)
    if lister is None:
        raise RuntimeError(fetch_failed_message())
    rows = await lister()
    models: list[dict[str, Any]] = []
    for item in rows or []:
        entry = catalog_entry(item)
        if entry is None:
            continue
        provider = entry.get("provider")
        if provider not in (None, "cursor"):
            continue
        entry.pop("provider", None)
        models.append(entry)
    if not models:
        raise RuntimeError(fetch_failed_message())
    return models


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


async def complete_chat(
    provider: str, key: str, model: str, prompt: str, max_tokens: int = 2048
) -> str:
    spec = PROVIDERS_BY_ID[provider]
    if spec.style == "anthropic":
        headers = {
            "x-api-key": key.strip(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": model,
            "max_tokens": max_tokens,
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
        "max_tokens": max_tokens,
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
