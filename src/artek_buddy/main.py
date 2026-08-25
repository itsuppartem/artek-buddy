from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from artek_buddy.bus import EventHub
from artek_buddy.computer.service import (
    ComputerService,
)
from artek_buddy.config import get_settings
from artek_buddy.consent import ConsentHub
from artek_buddy.contracts import (
    HealthResponse,
)
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.memory_book import HostBookRewriter
from artek_buddy.memory_gateway import GatewayClient
from artek_buddy.memory_hub import MemoryHub
from artek_buddy.observe import RequestContextMiddleware, configure_logging
from artek_buddy.runtime import (
    open_runtime,
    runtime_kind,
)
from artek_buddy.subagents import SubagentService

configure_logging()
log = logging.getLogger("artek_buddy")


from artek_buddy.http.bots import router as bots_router
from artek_buddy.http.computer import router as computer_router
from artek_buddy.http.connections import router as connections_router
from artek_buddy.http.consents import router as consents_router
from artek_buddy.http.devices import router as devices_router
from artek_buddy.http.memory import router as memory_router
from artek_buddy.http.models import router as models_router
from artek_buddy.http.routines import router as routines_router
from artek_buddy.http.session import router as session_router
from artek_buddy.http.threads import router as threads_router
from artek_buddy.http.turns import (
    _handle_bot_ask,
    _handle_takeover_request,
    _kick_inbox,
    _shutdown_work,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = HistoryStore(settings.database_url)
    try:
        store.open()
        store.apply_migrations()
        store.seed_env_cursor(settings.cursor_api_key)
        store.seed_env_connection_key(settings.composio_api_key)
        if runtime_kind(settings) == "scripted" and store.raw_key("cursor"):
            store.replace_catalog("cursor", ["scripted"])
        log.info("postgres ready")
    except DatabaseUnavailable:
        log.exception("postgres unavailable at boot; history routes will return 503")

    computers = ComputerService(store, settings)
    try:
        async with open_runtime(settings, store, computers) as runtime:
            try:
                store.ensure_workspace()
                leftover = store.fail_orphaned_runs()
                if leftover:
                    log.warning("marked %s leftover run(s) failed after restart", leftover)
                reaped = computers.reap_orphan_computers()
                if reaped:
                    log.warning("destroyed %s computer(s) with no remaining bot", reaped)
            except DatabaseUnavailable:
                log.exception("workspace setup skipped; postgres unavailable")
            app.state.settings = settings
            app.state.runtime = runtime
            app.state.store = store
            app.state.computers = computers
            app.state.hub = EventHub()
            app.state.active_turns = {}
            memory = MemoryHub(
                store,
                GatewayClient(settings.memory_gateway_url),
                rewriter=HostBookRewriter(store),
            )
            runtime.memory = memory
            app.state.memory = memory
            consent = ConsentHub(store, app.state.hub, settings)
            runtime.consent = consent
            app.state.consent = consent
            subagents = SubagentService(store, runtime)
            subagents.bind(app.state.hub, asyncio.get_running_loop())
            runtime.subagents = subagents
            runtime.events = app.state.hub
            runtime.loop = asyncio.get_running_loop()
            app.state.subagents = subagents
            runtime.on_takeover_requested = _handle_takeover_request
            runtime.on_bot_ask = _handle_bot_ask
            try:
                for bot in store.list_bots():
                    asyncio.create_task(
                        _kick_inbox(store, runtime, app.state.hub, bot),
                        name=f"inbox-recover-{bot.id}",
                    )
            except DatabaseUnavailable:
                log.exception("inbox recovery skipped; postgres unavailable")
            log.info(
                "listening on %s:%s runtime=%s default_agent=%s",
                settings.http_host,
                settings.http_port,
                runtime_kind(settings),
                runtime.default_agent_id,
            )
            yield
            await _shutdown_work()
    finally:
        store.close()


app = FastAPI(
    title="Artek Buddy",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(RequestContextMiddleware)

app.include_router(devices_router)
app.include_router(session_router)
app.include_router(models_router)
app.include_router(bots_router)
app.include_router(threads_router)
app.include_router(consents_router)
app.include_router(memory_router)
app.include_router(routines_router)
app.include_router(connections_router)
app.include_router(computer_router)


@app.get("/health")
async def health() -> HealthResponse:
    current = getattr(app.state, "runtime", None)
    history = getattr(app.state, "store", None)
    db_ok = False
    if history is not None:
        try:
            db_ok = history.available()
        except Exception:
            db_ok = False
    return HealthResponse(
        ok=current is not None,
        db=db_ok,
    )
