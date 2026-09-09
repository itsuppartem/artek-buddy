from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from artek_buddy.bot_credentials import (
    BotCredentialStore,
    CredentialStoreError,
    provider_slug,
)
from artek_buddy.contracts import (
    BotCredential,
    BotCredentialList,
    OkResponse,
    SaveBotCredentialInput,
)
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.http.deps import _db_error, _require_bot, credentials, require_auth, store

router = APIRouter()


def _row(status) -> BotCredential:
    return BotCredential(
        provider=status.provider,
        scope=status.scope,
        last_four=status.last_four,
        updated_at=status.updated_at,
        env_name=status.env_name or "",
    )


def _require_provider(provider: str) -> str:
    slug = provider_slug(provider)
    if slug is None:
        raise HTTPException(status_code=400, detail="unknown provider")
    return slug


@router.get("/v1/bots/{bot_id}/credentials", dependencies=[Depends(require_auth)])
async def list_bot_credentials(
    bot_id: str,
    history: HistoryStore = Depends(store),
    vault: BotCredentialStore = Depends(credentials),
) -> BotCredentialList:
    try:
        _require_bot(history, bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    try:
        rows = vault.list_for_bot(bot_id)
    except CredentialStoreError as err:
        raise HTTPException(status_code=503, detail="credential broker unavailable") from err
    return BotCredentialList(credentials=[_row(item) for item in rows])


@router.put("/v1/bots/{bot_id}/credentials/{provider}", dependencies=[Depends(require_auth)])
async def save_bot_credential(
    bot_id: str,
    provider: str,
    body: SaveBotCredentialInput,
    history: HistoryStore = Depends(store),
    vault: BotCredentialStore = Depends(credentials),
) -> BotCredential:
    slug = _require_provider(provider)
    try:
        _require_bot(history, bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    try:
        status = vault.put(bot_id, slug, body.secret)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except CredentialStoreError as err:
        raise HTTPException(status_code=503, detail="credential broker unavailable") from err
    return _row(status)


@router.delete("/v1/bots/{bot_id}/credentials/{provider}", dependencies=[Depends(require_auth)])
async def forget_bot_credential(
    bot_id: str,
    provider: str,
    history: HistoryStore = Depends(store),
    vault: BotCredentialStore = Depends(credentials),
) -> OkResponse:
    slug = _require_provider(provider)
    try:
        _require_bot(history, bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    try:
        vault.forget(bot_id, slug)
    except CredentialStoreError as err:
        raise HTTPException(status_code=503, detail="credential broker unavailable") from err
    return OkResponse(ok=True)
