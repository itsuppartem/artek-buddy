from __future__ import annotations

import hmac
import logging
import secrets
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from artek_buddy.auth import pairing_attempts
from artek_buddy.config import Settings
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.http.deps import _db_error, current_app, settings, store
from artek_buddy.owner_clients import OWNER_WEB_ERROR
from artek_buddy.web_files import resolve_web_root, safe_content_type, web_file_for_request

log = logging.getLogger("artek_buddy")

COOKIE_NAME = "artek_device"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60
NONCE_HEADER = "X-Artek-Local-Nonce"

router = APIRouter()


def _page_nonce() -> str:
    app = current_app()
    nonce = getattr(app.state, "page_nonce", None)
    if not nonce:
        nonce = secrets.token_urlsafe(24)
        app.state.page_nonce = nonce
    return str(nonce)


def _cookie_secure(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    return forwarded == "https"


def _same_origin(request: Request, *, mutating: bool) -> bool:
    origin = (request.headers.get("origin") or "").strip()
    host = (request.headers.get("host") or "").strip()
    if not origin:
        return not mutating
    parsed = urlparse(origin)
    origin_host = parsed.netloc or parsed.hostname or ""
    return origin_host == host


def _require_local(request: Request, nonce: str | None, *, mutating: bool) -> None:
    if not _same_origin(request, mutating=mutating):
        raise HTTPException(status_code=403, detail="forbidden")
    if not mutating:
        return
    expected = _page_nonce()
    given = (nonce or "").strip()
    if not expected or not given or not hmac.compare_digest(given, expected):
        raise HTTPException(status_code=403, detail="forbidden")


def _set_device_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(request),
        path="/",
    )


def _clear_device_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/local/status")
async def page_status(request: Request) -> JSONResponse:
    _require_local(request, None, mutating=False)
    token = (request.cookies.get(COOKIE_NAME) or "").strip()
    paired = False
    if token:
        try:
            device = store().lookup_device_token(token)
        except DatabaseUnavailable as err:
            raise _db_error(err) from err
        paired = device is not None
    return JSONResponse(
        {
            "paired": paired,
            "url": "",
            "nonce": _page_nonce(),
            "surface": "host",
        }
    )


@router.post("/local/pair")
async def page_pair(
    request: Request,
    nonce: str | None = Header(default=None, alias=NONCE_HEADER),
    history: HistoryStore = Depends(store),
) -> JSONResponse:
    _require_local(request, nonce, mutating=True)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    code = str(body.get("pairing_code") or body.get("pairingCode") or "").strip()
    name = str(body.get("name") or "Phone").strip() or "Phone"
    platform = str(body.get("platform") or "web").strip() or "web"
    if not code:
        raise HTTPException(status_code=400, detail="pairing code required")
    key = request.client.host if request.client else "unknown"
    if not pairing_attempts.allow(key):
        raise HTTPException(
            status_code=429,
            detail="too many pairing attempts, try again in a few minutes",
        )
    try:
        ok = history.consume_pairing_code(code)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if not ok:
        pairing_attempts.record(key)
        raise HTTPException(status_code=403, detail="invalid or expired pairing code")
    try:
        created = history.create_device(name, platform)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    log.info("device created id=%s surface=host", created.id)
    payload = {
        "ok": True,
        "paired": True,
        "device": {"id": created.id, "name": created.name, "platform": created.platform},
    }
    response = JSONResponse(payload)
    _set_device_cookie(response, request, created.token)
    return response


@router.post("/local/unpair")
async def page_unpair(
    request: Request,
    nonce: str | None = Header(default=None, alias=NONCE_HEADER),
) -> JSONResponse:
    _require_local(request, nonce, mutating=True)
    response = JSONResponse({"ok": True, "paired": False})
    _clear_device_cookie(response)
    return response


@router.post("/local/owner-read")
@router.post("/local/owner-write")
@router.post("/local/owner-list")
@router.post("/local/owner-exec")
@router.post("/local/save-artifact")
@router.post("/local/save-home-file")
@router.post("/local/attach-files")
async def page_owner_cut(
    request: Request,
    nonce: str | None = Header(default=None, alias=NONCE_HEADER),
) -> None:
    _require_local(request, nonce, mutating=True)
    raise HTTPException(status_code=403, detail=OWNER_WEB_ERROR)


@router.post("/local/notify")
async def page_notify(
    request: Request,
    nonce: str | None = Header(default=None, alias=NONCE_HEADER),
) -> dict[str, bool]:
    _require_local(request, nonce, mutating=True)
    return {"ok": False}


@router.get("/")
@router.get("/{full_path:path}")
async def page_files(full_path: str = "", cfg: Settings = Depends(settings)) -> FileResponse:
    reserved = ("v1/", "local/", "health", "novnc/")
    if full_path == "health" or full_path.startswith(reserved):
        raise HTTPException(status_code=404, detail="not found")
    root = resolve_web_root(cfg.web_root)
    if root is None:
        raise HTTPException(status_code=404, detail="page is not packaged")
    path = web_file_for_request(root, f"/{full_path}" if full_path else "/")
    if path is None:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type=safe_content_type(path))
