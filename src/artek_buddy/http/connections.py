from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from artek_buddy.connections.broker import (
    MAX_KEY_CHARS,
    fake_broker,
    hide_secret,
    host_callback,
)
from artek_buddy.connections.http import HttpBroker
from artek_buddy.contracts import (
    BeginConnectionInput,
    BeginConnectionResult,
    Connection,
    ConnectionCatalog,
    ConnectionKeyInput,
    ConnectionKeyStatus,
    ConnectionList,
    OkResponse,
)
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.http.deps import _db_error, require_auth, settings, store
from artek_buddy.model_catalog import is_placeholder_key
from artek_buddy.runtime.factory import runtime_kind

router = APIRouter()
MISSING_KEY = "paste a key in Plugins"


def _broker(cfg, key: str):
    if runtime_kind(cfg) == "scripted":
        return fake_broker()
    return HttpBroker(key)


def _require_key(history: HistoryStore) -> str:
    key = history.raw_connection_key()
    if not key:
        raise HTTPException(status_code=409, detail=MISSING_KEY)
    return key


@router.get("/v1/connections/status", dependencies=[Depends(require_auth)])
async def connection_status(history: HistoryStore = Depends(store)) -> ConnectionKeyStatus:
    try:
        return history.connection_key_status()
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/connections/key", dependencies=[Depends(require_auth)])
async def set_connection_key(
    body: ConnectionKeyInput,
    history: HistoryStore = Depends(store),
) -> ConnectionKeyStatus:
    incoming = (body.api_key or "").strip()
    if not incoming or is_placeholder_key(incoming) or len(incoming) > MAX_KEY_CHARS:
        raise HTTPException(status_code=400, detail="API key is empty")
    try:
        return history.save_connection_key(incoming)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.delete("/v1/connections/key", dependencies=[Depends(require_auth)])
async def clear_connection_key(history: HistoryStore = Depends(store)) -> OkResponse:
    try:
        history.clear_connection_key()
        return OkResponse(ok=True)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.get("/v1/connections/catalog", dependencies=[Depends(require_auth)])
async def connection_catalog(
    q: str | None = None,
    history: HistoryStore = Depends(store),
    cfg=Depends(settings),
) -> ConnectionCatalog:
    try:
        key = _require_key(history)
        items = _broker(cfg, key).catalog(q, history.connected_slugs())
        return ConnectionCatalog(items=items)
    except HTTPException:
        raise
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    except Exception as err:
        secret = history.raw_connection_key() or ""
        raise HTTPException(status_code=502, detail=hide_secret(str(err), secret)) from err


@router.get("/v1/connections", dependencies=[Depends(require_auth)])
async def list_connections(history: HistoryStore = Depends(store)) -> ConnectionList:
    try:
        _require_key(history)
        return history.list_connections()
    except HTTPException:
        raise
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/connections", dependencies=[Depends(require_auth)])
async def begin_connection(
    body: BeginConnectionInput,
    history: HistoryStore = Depends(store),
    cfg=Depends(settings),
) -> BeginConnectionResult:
    provider = (body.provider or "").strip().lower()
    try:
        key = _require_key(history)
        _ = body.redirect_url
        try:
            redirect = host_callback(cfg.connections_callback_url)
        except ValueError:
            raise HTTPException(
                status_code=503,
                detail="set CONNECTIONS_CALLBACK_URL to this host's https origin",
            ) from None
        if history.active_for_provider(provider) is not None:
            raise HTTPException(status_code=409, detail="already connected")
        broker = _broker(cfg, key)
        try:
            started = broker.begin(provider, redirect)
        except KeyError:
            raise HTTPException(status_code=404, detail="app not found") from None
        except ValueError:
            raise HTTPException(status_code=400, detail="redirect url is invalid") from None
        except Exception as err:
            raise HTTPException(status_code=502, detail=hide_secret(str(err), key)) from err
        connection = history.insert_connection(
            provider=provider,
            display_name=started.display_name,
            status=started.status,
            capabilities=started.capabilities,
            no_auth=started.no_auth,
            remote_id=started.remote_id,
        )
        return BeginConnectionResult(
            connection=connection,
            authorization_url=started.authorization_url,
        )
    except HTTPException:
        raise
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/connections/{connection_id}/complete", dependencies=[Depends(require_auth)])
async def complete_connection(
    connection_id: str,
    history: HistoryStore = Depends(store),
    cfg=Depends(settings),
) -> Connection:
    try:
        key = _require_key(history)
        current = history.get_connection(connection_id)
        if current is None:
            raise HTTPException(status_code=404, detail="connection not found")
        remote_id = history.connection_remote_id(connection_id)
        if not remote_id:
            raise HTTPException(status_code=404, detail="connection not found")
        broker = _broker(cfg, key)
        try:
            status = broker.complete(remote_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="connection not found") from None
        except Exception as err:
            raise HTTPException(status_code=502, detail=hide_secret(str(err), key)) from err
        caps = current.capabilities
        if status == "connected" and not caps:
            caps = [spec.name for spec in broker.tool_specs([current.provider])]
        updated = history.update_connection(connection_id, status=status, capabilities=caps)
        if updated is None:
            raise HTTPException(status_code=404, detail="connection not found")
        return updated
    except HTTPException:
        raise
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/connections/{connection_id}/revoke", dependencies=[Depends(require_auth)])
async def revoke_connection(
    connection_id: str,
    history: HistoryStore = Depends(store),
    cfg=Depends(settings),
) -> OkResponse:
    try:
        key = _require_key(history)
        current = history.get_connection(connection_id)
        if current is None:
            raise HTTPException(status_code=404, detail="connection not found")
        broker = _broker(cfg, key)
        remote_id = history.connection_remote_id(connection_id)
        try:
            if remote_id:
                broker.revoke(remote_id)
        except Exception:
            pass
        history.update_connection(connection_id, status="revoked", capabilities=[])
        return OkResponse(ok=True)
    except HTTPException:
        raise
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
