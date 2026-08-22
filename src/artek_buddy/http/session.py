from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends

from artek_buddy.contracts import (
    DeploymentSettings,
    Me,
    SessionRequest,
    SessionResponse,
    UpdateDeploymentInput,
)
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.db.shaping import (
    DEFAULT_BOT_NAME,
)
from artek_buddy.runtime import (
    AgentRuntime,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("artek_buddy")

from fastapi import APIRouter

from artek_buddy.http.deps import (
    _db_error,
    require_auth,
    runtime,
    store,
)

router = APIRouter()


@router.get("/v1/models", dependencies=[Depends(require_auth)])
async def list_models(rt: AgentRuntime = Depends(runtime)) -> dict[str, Any]:
    return {"models": await rt.list_models()}


@router.get("/v1/session", dependencies=[Depends(require_auth)])
async def get_session(
    rt: AgentRuntime = Depends(runtime),
    history: HistoryStore = Depends(store),
) -> SessionResponse:
    try:
        bot = history.default_bot(rt.default_agent_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return SessionResponse(
        agent_id=rt.default_agent_id or "",
        bot_id=bot.id if bot else None,
        thread_id=bot.thread_id if bot else None,
    )


@router.post("/v1/session", dependencies=[Depends(require_auth)])
async def create_session(
    body: SessionRequest,
    rt: AgentRuntime = Depends(runtime),
    history: HistoryStore = Depends(store),
) -> SessionResponse:
    agent_id = await rt.create_session(name=body.name, persist_default=True)
    try:
        bot = history.create_bot(name=body.name or DEFAULT_BOT_NAME, cursor_agent_id=agent_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return SessionResponse(agent_id=agent_id, bot_id=bot.id, thread_id=bot.thread_id)


@router.get("/v1/me", dependencies=[Depends(require_auth)])
async def get_me() -> Me:
    return Me()


@router.get("/v1/deployment", dependencies=[Depends(require_auth)])
async def get_deployment() -> DeploymentSettings:
    return DeploymentSettings()


@router.patch("/v1/deployment", dependencies=[Depends(require_auth)])
async def update_deployment(body: UpdateDeploymentInput) -> DeploymentSettings:
    return DeploymentSettings(
        signups_enabled=body.signups_enabled if body.signups_enabled is not None else True,
        signup_allowlist=body.signup_allowlist if body.signup_allowlist is not None else [],
        computer_host=body.computer_host if body.computer_host is not None else "docker",
    )
