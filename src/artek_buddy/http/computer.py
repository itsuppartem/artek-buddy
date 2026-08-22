from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Query, Request, WebSocket
from fastapi.responses import FileResponse, Response

from artek_buddy.bus import EventHub
from artek_buddy.computer.proxy import proxy_novnc_http, proxy_novnc_ws
from artek_buddy.computer.service import (
    ComputerBusy,
    ComputerError,
    ComputerService,
)
from artek_buddy.contracts import (
    ComputerFileContent,
    ComputerFileList,
    ComputerInput,
    ComputerStatus,
    OkResponse,
    ProductEventType,
    ScreenUrlResult,
    TakeoverResult,
)
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.runtime import (
    AgentRuntime,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("artek_buddy")

from fastapi import APIRouter

from artek_buddy.http.deps import (
    _authorize_websocket,
    _computer_http,
    _db_error,
    _require_bot,
    computers,
    hub,
    require_auth,
    runtime,
    store,
)
from artek_buddy.http.turns import (
    _emit,
    _emit_computer,
    _resume_parked_takeover,
)

router = APIRouter()


@router.get("/v1/computer/{bot_id}", dependencies=[Depends(require_auth)])
async def computer_status(
    bot_id: str,
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> ComputerStatus:
    try:
        return boxes.status(_require_bot(history, bot_id))
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/computer/{bot_id}/boot", dependencies=[Depends(require_auth)])
async def computer_boot(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
    boxes: ComputerService = Depends(computers),
) -> ComputerStatus:
    try:
        bot = _require_bot(history, bot_id)
        status = boxes.boot(bot)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    _emit_computer(events, bot, status)
    return status


@router.post("/v1/computer/{bot_id}/stop", dependencies=[Depends(require_auth)])
async def computer_stop(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
    boxes: ComputerService = Depends(computers),
) -> ComputerStatus:
    try:
        bot = _require_bot(history, bot_id)
        status = boxes.stop(bot)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    _emit_computer(events, bot, status)
    return status


@router.post("/v1/computer/{bot_id}/restart", dependencies=[Depends(require_auth)])
async def computer_restart(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
    boxes: ComputerService = Depends(computers),
) -> ComputerStatus:
    try:
        bot = _require_bot(history, bot_id)
        status = boxes.restart(bot)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    _emit_computer(events, bot, status)
    return status


@router.post("/v1/computer/{bot_id}/reset", dependencies=[Depends(require_auth)])
async def computer_reset(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
    boxes: ComputerService = Depends(computers),
) -> ComputerStatus:
    try:
        bot = _require_bot(history, bot_id)
        status = boxes.reset(bot)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    _emit_computer(events, bot, status)
    return status


@router.post("/v1/computer/{bot_id}/takeover", dependencies=[Depends(require_auth)])
async def computer_takeover(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
    boxes: ComputerService = Depends(computers),
) -> TakeoverResult:
    try:
        bot = _require_bot(history, bot_id)
        result = boxes.takeover(bot)
        status = boxes.status(bot)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    _emit(
        events,
        bot,
        ProductEventType.COMPUTER_TAKEOVER_GRANTED,
        {"lease_id": result.lease_id, "expires_at": result.expires_at},
    )
    _emit_computer(events, bot, status)
    return result


@router.post("/v1/computer/{bot_id}/release", dependencies=[Depends(require_auth)])
async def computer_release(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
    boxes: ComputerService = Depends(computers),
    rt: AgentRuntime = Depends(runtime),
) -> OkResponse:
    try:
        bot = _require_bot(history, bot_id)
        status = boxes.release(bot)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    _emit(events, bot, ProductEventType.COMPUTER_TAKEOVER_RELEASED, {})
    _emit_computer(events, bot, status)
    try:
        _resume_parked_takeover(history, rt, events, bot)
    except Exception:
        log.exception("failed to resume after release")
    return OkResponse(ok=True)


@router.post("/v1/computer/{bot_id}/heartbeat", dependencies=[Depends(require_auth)])
async def computer_heartbeat(
    bot_id: str,
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> OkResponse:
    try:
        boxes.heartbeat(_require_bot(history, bot_id))
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return OkResponse(ok=True)


@router.get("/v1/computer/{bot_id}/screen", dependencies=[Depends(require_auth)])
async def computer_screen(
    bot_id: str,
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> ScreenUrlResult:
    try:
        return boxes.screen_url(_require_bot(history, bot_id))
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/computer/{bot_id}/input", dependencies=[Depends(require_auth)])
async def computer_input(
    bot_id: str,
    body: ComputerInput,
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> OkResponse:
    try:
        boxes.send_input(_require_bot(history, bot_id), body.kind, body.payload)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return OkResponse(ok=True)


@router.get("/v1/computer/{bot_id}/files", dependencies=[Depends(require_auth)])
async def computer_files(
    bot_id: str,
    path: str = Query(default="/"),
    hidden: bool = Query(default=False),
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> ComputerFileList:
    try:
        return boxes.list_files(_require_bot(history, bot_id), path, hidden=hidden)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.get("/v1/computer/{bot_id}/files/read", dependencies=[Depends(require_auth)])
async def computer_read_file(
    bot_id: str,
    path: str = Query(...),
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> ComputerFileContent:
    try:
        return boxes.read_file(_require_bot(history, bot_id), path)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.get("/v1/computer/{bot_id}/files/raw", dependencies=[Depends(require_auth)])
async def computer_download_file(
    bot_id: str,
    path: str = Query(...),
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> FileResponse:
    try:
        target, name, mime = boxes.file_for_download(_require_bot(history, bot_id), path)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return FileResponse(target, filename=name, media_type=mime)


@router.api_route(
    "/novnc/{rest:path}",
    methods=["GET", "HEAD"],
    dependencies=[Depends(require_auth)],
    include_in_schema=False,
)
async def novnc_http(rest: str, request: Request) -> Response:
    return await proxy_novnc_http(request, request.app.state.settings.agent_http_token)


@router.websocket("/novnc/{rest:path}")
async def novnc_ws(websocket: WebSocket, rest: str) -> None:
    try:
        await _authorize_websocket(websocket)
    except HTTPException as err:
        code = 4401 if err.status_code == 401 else 4403
        await websocket.close(code=code)
        return
    await proxy_novnc_ws(websocket, websocket.app.state.settings.agent_http_token)
