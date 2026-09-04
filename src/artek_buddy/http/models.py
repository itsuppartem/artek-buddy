from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from artek_buddy.bus import EventHub
from artek_buddy.contracts import (
    ConnectModelInput,
    ModelCredential,
    ModelCredentialList,
    ModelInfo,
    ModelListResponse,
    OkResponse,
    SetDefaultModelInput,
)
from artek_buddy.contracts.events import ProductEvent, ProductEventType
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.db.shaping import isoformat_utc, new_id
from artek_buddy.http.deps import _db_error, hub, require_auth, runtime, settings, store
from artek_buddy.model_catalog import (
    fetch_cursor_models,
    fetch_failed_message,
    fetch_models,
    is_placeholder_key,
    preferred_model,
    unknown_provider,
)
from artek_buddy.model_switch import default_model_line
from artek_buddy.runtime.factory import runtime_kind
from artek_buddy.runtime.protocol import AgentRuntime

router = APIRouter()


def _scripted(cfg) -> bool:
    return runtime_kind(cfg) == "scripted"


@router.get("/v1/models", dependencies=[Depends(require_auth)])
async def list_models(history: HistoryStore = Depends(store)) -> ModelListResponse:
    try:
        rows = [
            ModelInfo(id=item["id"], provider=item["provider"]) for item in history.list_catalog()
        ]
        return ModelListResponse(models=rows)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.get("/v1/models/credentials", dependencies=[Depends(require_auth)])
async def list_credentials(history: HistoryStore = Depends(store)) -> ModelCredentialList:
    try:
        return history.list_credentials()
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


async def _catalog(provider: str, key: str, cfg, rt: AgentRuntime) -> list[str]:
    if _scripted(cfg):
        return await fetch_models(provider, key, scripted=True)
    if provider == "cursor":
        return await fetch_cursor_models(key, rt)
    return await fetch_models(provider, key, scripted=False)


@router.post("/v1/models/credentials", dependencies=[Depends(require_auth)])
async def connect_model(
    body: ConnectModelInput,
    history: HistoryStore = Depends(store),
    cfg=Depends(settings),
    rt: AgentRuntime = Depends(runtime),
) -> ModelCredential:
    if unknown_provider(body.provider):
        raise HTTPException(status_code=400, detail="unknown provider")
    try:
        incoming = (body.api_key or "").strip()
        if incoming:
            if is_placeholder_key(incoming):
                raise HTTPException(status_code=400, detail="API key is empty")
            history.save_key(body.provider, incoming)
            key = incoming
        else:
            key = history.raw_key(body.provider)
            if not key:
                raise HTTPException(status_code=400, detail="API key is empty")
        try:
            models = await _catalog(body.provider, key, cfg, rt)
        except PermissionError as err:
            return history.set_credential_error(body.provider, str(err))
        except Exception:
            return history.set_credential_error(body.provider, fetch_failed_message())
        history.replace_catalog(body.provider, models)
        picked = preferred_model(models)
        if picked and history.get_default_model() is None:
            if body.provider == "cursor":
                history.set_default_model(
                    body.provider,
                    picked,
                    effort=cfg.cursor_model_effort,
                    fast=cfg.cursor_model_fast,
                )
            else:
                history.set_default_model(body.provider, picked)
        return history.set_credential_error(body.provider, None)
    except HTTPException:
        raise
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.delete("/v1/models/credentials/{provider}", dependencies=[Depends(require_auth)])
async def forget_model(provider: str, history: HistoryStore = Depends(store)) -> OkResponse:
    if unknown_provider(provider):
        raise HTTPException(status_code=400, detail="unknown provider")
    try:
        history.forget_key(provider)
        return OkResponse(ok=True)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/models/default", dependencies=[Depends(require_auth)])
async def set_default_model(
    body: SetDefaultModelInput,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
    rt: AgentRuntime = Depends(runtime),
) -> OkResponse:
    if unknown_provider(body.provider):
        raise HTTPException(status_code=400, detail="unknown provider")
    try:
        if body.model not in history.catalog_ids(body.provider):
            raise HTTPException(status_code=400, detail="model is not on this provider's list")
        before = (history.get_default_model(), history.get_model_params())
        history.set_default_model(body.provider, body.model, effort=body.effort, fast=body.fast)
        after = (history.get_default_model(), history.get_model_params())
        if body.bot_id and after != before:
            _write_default_meta(history, events, body.bot_id, body.model)
            bot = history.get_bot(body.bot_id)
            if bot is not None and not history.has_active_run(bot.id):
                from artek_buddy.http.turns import _ensure_agent

                await _ensure_agent(history, rt, bot)
        return OkResponse(ok=True)
    except HTTPException:
        raise
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


def _write_default_meta(history: HistoryStore, events: EventHub, bot_id: str, model: str) -> None:
    bot = history.get_bot(bot_id)
    if bot is None:
        return
    effort, fast = history.get_model_params()
    live = history.has_active_run(bot.id)
    text = default_model_line(model, effort, fast, live=live)
    msg = history.append_bot_message(bot, [{"kind": "meta", "text": text}])
    events.publish(
        ProductEvent(
            id=new_id("evt"),
            workspace_id=bot.workspace_id,
            thread_id=bot.thread_id,
            bot_id=bot.id,
            seq=events.next_seq(bot.id),
            type=ProductEventType.THREAD_MESSAGE_CREATED,
            created_at=isoformat_utc(),
            payload={"message": msg.model_dump(mode="json")},
        )
    )
