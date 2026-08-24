from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from artek_buddy.contracts import (
    ConnectModelInput,
    ModelCredential,
    ModelCredentialList,
    ModelInfo,
    ModelListResponse,
    OkResponse,
    SetDefaultModelInput,
)
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.http.deps import _db_error, require_auth, runtime, settings, store
from artek_buddy.model_catalog import (
    fetch_cursor_models,
    fetch_failed_message,
    fetch_models,
    is_placeholder_key,
    unknown_provider,
)
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
) -> OkResponse:
    if unknown_provider(body.provider):
        raise HTTPException(status_code=400, detail="unknown provider")
    try:
        if body.model not in history.catalog_ids(body.provider):
            raise HTTPException(status_code=400, detail="model is not on this provider's list")
        history.set_default_model(body.provider, body.model)
        return OkResponse(ok=True)
    except HTTPException:
        raise
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
