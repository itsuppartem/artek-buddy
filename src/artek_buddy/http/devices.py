from __future__ import annotations

import logging

from fastapi import Depends, Header, HTTPException, Request

from artek_buddy.auth import host_token_match, pairing_attempts
from artek_buddy.config import Settings
from artek_buddy.contracts import (
    CreateDeviceInput,
    Device,
    DeviceCreated,
    DeviceList,
    PairingCode,
)
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("artek_buddy")

from fastapi import APIRouter

from artek_buddy.http.deps import (
    _bearer,
    _db_error,
    require_auth,
    require_host,
    settings,
    store,
)

router = APIRouter()


@router.post("/v1/devices/pairing", dependencies=[Depends(require_host)])
async def create_pairing(history: HistoryStore = Depends(store)) -> PairingCode:
    try:
        return history.create_pairing_code()
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/devices")
async def create_device(
    request: Request,
    body: CreateDeviceInput,
    authorization: str | None = Header(default=None),
    cfg: Settings = Depends(settings),
    history: HistoryStore = Depends(store),
) -> DeviceCreated:
    pairing = (body.pairing_code or "").strip()
    token = _bearer(authorization)
    if pairing:
        key = request.client.host if request.client else "unknown"
        if not pairing_attempts.allow(key):
            raise HTTPException(
                status_code=429,
                detail="too many pairing attempts, try again in a few minutes",
            )
        try:
            ok = history.consume_pairing_code(pairing)
        except DatabaseUnavailable as err:
            raise _db_error(err) from err
        if not ok:
            pairing_attempts.record(key)
            raise HTTPException(status_code=403, detail="invalid or expired pairing code")
    elif token is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    elif not host_token_match(token, cfg.agent_http_token):
        raise HTTPException(status_code=403, detail="host token or pairing code required")
    try:
        created = history.create_device(body.name, body.platform)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    log.info("device created id=%s", created.id)
    return created


@router.get("/v1/devices", dependencies=[Depends(require_auth)])
async def list_devices(history: HistoryStore = Depends(store)) -> DeviceList:
    try:
        return DeviceList(devices=history.list_devices())
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.delete("/v1/devices/{device_id}")
async def revoke_device(
    device_id: str,
    actor: str = Depends(require_auth),
    history: HistoryStore = Depends(store),
) -> Device:
    if actor != "host" and actor != device_id:
        raise HTTPException(status_code=403, detail="cannot revoke another device")
    try:
        device = history.revoke_device(device_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")
    return device
