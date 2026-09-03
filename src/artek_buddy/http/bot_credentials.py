from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException

from artek_buddy.bot_credentials import PROVIDERS, BotCredentialStore
from artek_buddy.config import Settings
from artek_buddy.contracts import (
    BotCredential,
    BotCredentialList,
    OkResponse,
    SaveBotCredentialInput,
)
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.http.deps import _db_error, _require_bot, require_auth, settings, store

router = APIRouter()


def _vault(cfg: Settings) -> BotCredentialStore:
    return BotCredentialStore(cfg.agent_data_dir)


def _row(status) -> BotCredential:
    provider = cast(Literal["github", "pypi"], status.provider)
    return BotCredential(
        provider=provider,
        scope=status.scope,
        last_four=status.last_four,
        updated_at=status.updated_at,
    )


@router.get("/v1/bots/{bot_id}/credentials", dependencies=[Depends(require_auth)])
async def list_bot_credentials(
    bot_id: str,
    history: HistoryStore = Depends(store),
    cfg: Settings = Depends(settings),
) -> BotCredentialList:
    try:
        _require_bot(history, bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return BotCredentialList(credentials=[_row(item) for item in _vault(cfg).list_for_bot(bot_id)])


@router.put("/v1/bots/{bot_id}/credentials/{provider}", dependencies=[Depends(require_auth)])
async def save_bot_credential(
    bot_id: str,
    provider: str,
    body: SaveBotCredentialInput,
    history: HistoryStore = Depends(store),
    cfg: Settings = Depends(settings),
) -> BotCredential:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="unknown provider")
    try:
        _require_bot(history, bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    try:
        status = _vault(cfg).put(bot_id, provider, body.secret)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return _row(status)


@router.delete("/v1/bots/{bot_id}/credentials/{provider}", dependencies=[Depends(require_auth)])
async def forget_bot_credential(
    bot_id: str,
    provider: str,
    history: HistoryStore = Depends(store),
    cfg: Settings = Depends(settings),
) -> OkResponse:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="unknown provider")
    try:
        _require_bot(history, bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    _vault(cfg).forget(bot_id, provider)
    return OkResponse(ok=True)
