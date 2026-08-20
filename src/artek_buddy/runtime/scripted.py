from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from artek_buddy.config import Settings
from artek_buddy.consent import CLASS_BROWSE, CLASS_OWNER_EXEC, CLASS_PAGE, OWNER_HOME_SCOPE
from artek_buddy.db.shaping import new_id
from artek_buddy.runtime.base import RuntimeBase
from artek_buddy.runtime.tools import ProductTools
from artek_buddy.runtime.types import AgentRuntimeError, ProductStreamEvent, RunRecord
from artek_buddy.stream import _map_tool_to_events

log = logging.getLogger("artek_buddy")

E2E_DRAFT_LEAK = "grade's current weather from a public API"
E2E_DRAFT_ANSWER = "Belgrade is 22°C and clear."
E2E_CLOSE_STATUS = "Closing Chromium"
E2E_SLOW_ANSWER = "slow done"
E2E_MARKDOWN_ANSWER = "**Belgrade** weather is 22C"
E2E_ASK_QUESTION = "Which city?"
E2E_ASK_FREE_QUESTION = "What should I call you?"
E2E_FAIL_ERROR = "scripted fail"
E2E_META_TEXT = "Remembered: Prefers short answers without emoji"
E2E_PROGRESS_TEXT = "Checking the desktop"
E2E_CARD_KEY = "City"
E2E_CARD_VALUE = "Belgrade"
E2E_COMPUTER_TEXT = "Opened Chromium"
E2E_CHILD_NAME = "Spawned pal"
E2E_CHILD_ARCHIVED = "Old pal"
E2E_SUBAGENT_NAME = "Researcher"
E2E_SUBAGENT_TASK = "please e2e-slow now"
E2E_OLDER_PREFIX = "e2e-old-"
E2E_OLDER_COUNT = 51
E2E_HANG_S = 12.0


@dataclass
class ScriptedStep:
    event: tuple[str, dict[str, Any]] | None = None
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    consent: dict[str, Any] | None = None
    blocks: list[dict[str, Any]] | None = None
    result: str | None = None
    status: str | None = None
    error: str | None = None
    raise_error: str | None = None
    delay_s: float | None = None


def scripted_consent(
    *,
    action_class: str,
    scope_key: str,
    summary: str,
    detail: str | None = None,
) -> ScriptedStep:
    return ScriptedStep(
        consent={
            "action_class": action_class,
            "scope_key": scope_key,
            "summary": summary,
            "detail": detail,
        }
    )


def scripted_text(text: str) -> ScriptedStep:
    return ScriptedStep(event=("thread.message.updated", {"text": text, "kind": "text", "replace": True}))


def scripted_progress(text: str, kind: str = "thinking") -> ScriptedStep:
    return ScriptedStep(event=("thread.progress", {"text": text, "kind": kind, "replace": True}))


def scripted_tool(tool: str, **args: Any) -> ScriptedStep:
    return ScriptedStep(tool=tool, args=dict(args))


def scripted_delay(seconds: float) -> ScriptedStep:
    return ScriptedStep(delay_s=seconds)


def scripted_finish(result: str = "ok", status: str = "completed", error: str | None = None) -> ScriptedStep:
    return ScriptedStep(result=result, status=status, error=error)


def scripted_blocks(*blocks: dict[str, Any]) -> ScriptedStep:
    return ScriptedStep(blocks=list(blocks))


def _bind_block_values(value: Any, bot_id: str | None) -> Any:
    if value == "$bot":
        return bot_id or "bot_unknown"
    if isinstance(value, dict):
        return {key: _bind_block_values(item, bot_id) for key, item in value.items()}
    if isinstance(value, list):
        return [_bind_block_values(item, bot_id) for item in value]
    return value


def _user_tail(prompt: str) -> str:
    """Last wrap_turn_prompt segment is the user (or worker) text."""
    return (prompt or "").rsplit("\n\n", 1)[-1]


def steps_for_prompt(prompt: str) -> list[ScriptedStep]:
    text = prompt or ""
    user = _user_tail(text)
    hay = user.lower()
    if "e2e-hide-draft" in text:
        return [
            scripted_progress("planning the lookup"),
            scripted_text(E2E_DRAFT_LEAK),
            scripted_delay(0.6),
            scripted_finish(E2E_DRAFT_ANSWER),
        ]
    if "e2e-close-browser" in text:
        return [
            scripted_tool("send_message", text=E2E_CLOSE_STATUS),
            scripted_tool("close_app", application="chromium"),
            scripted_finish("browser closed"),
        ]
    if "e2e-remember" in hay:
        return [
            scripted_tool(
                "remember",
                content="Prefers short answers without emoji",
                kind="preference",
            ),
            scripted_finish("I'll remember that."),
        ]
    if "e2e-thread-blocks" in text:
        return [
            scripted_blocks(
                {"kind": "meta", "text": E2E_META_TEXT},
                {"kind": "progress", "text": E2E_PROGRESS_TEXT},
                {"kind": "card", "lines": [{"k": E2E_CARD_KEY, "v": E2E_CARD_VALUE}]},
                {"kind": "text", "text": "Working on the desktop."},
                {"kind": "computer", "state": "done", "text": E2E_COMPUTER_TEXT},
                {
                    "kind": "child_bot",
                    "bot_id": "$bot",
                    "name": E2E_CHILD_NAME,
                    "title": "helper",
                    "status": "created",
                },
                {
                    "kind": "child_bot",
                    "bot_id": "bot_gone",
                    "name": E2E_CHILD_ARCHIVED,
                    "title": None,
                    "status": "archived",
                },
            ),
            scripted_finish(""),
        ]
    if "e2e-ask-free" in text:
        return [
            scripted_blocks(
                {
                    "kind": "ask",
                    "text": E2E_ASK_FREE_QUESTION,
                    "status": "pending",
                }
            ),
            scripted_finish(""),
        ]
    if "e2e-ask" in text:
        return [
            scripted_tool(
                "ask_user",
                question=E2E_ASK_QUESTION,
                options=["Belgrade", "Berlin"],
            ),
            scripted_finish(""),
        ]
    if "e2e-subagent" in text:
        return [
            scripted_tool(
                "spawn_subagent",
                name=E2E_SUBAGENT_NAME,
                task=E2E_SUBAGENT_TASK,
            ),
            scripted_finish("worker started"),
        ]
    if "e2e-takeover" in text:
        return [
            ScriptedStep(event=("computer.takeover.requested", {})),
            scripted_finish("need you"),
        ]
    if "e2e-load-earlier" in text:
        return [
            *(
                scripted_blocks({"kind": "text", "text": f"{E2E_OLDER_PREFIX}{index:02d}"})
                for index in range(E2E_OLDER_COUNT)
            ),
            scripted_finish(""),
        ]
    if "e2e-hang" in text:
        return [scripted_delay(E2E_HANG_S), scripted_finish("hang done")]
    if "research a city" in hay or "which city should we research" in hay:
        return [
            scripted_progress("I need a city before I open sources."),
            scripted_delay(1.4),
            scripted_tool(
                "ask_user",
                question="Which city should we research?",
                detail="I can open Wikipedia on the desktop after you pick one.",
                options=["Belgrade", "Berlin"],
            ),
            scripted_finish(""),
        ]
    if "morning briefing" in hay:
        return [
            scripted_progress("checking the desktop and routines"),
            scripted_delay(2.2),
            scripted_finish(
                "Pi host is up. The desktop is idle. I can open Chromium, remember facts, "
                "and run a scheduled briefing. Take control if a login is needed."
            ),
        ]
    if user.strip() == "Belgrade":
        return [
            scripted_progress("pulling a short brief"),
            scripted_delay(2.0),
            scripted_finish(
                "Belgrade: Danube + Sava, Kalemegdan, and a dense cafe scene. "
                "I can keep sources open on this Pi desktop."
            ),
        ]
    if "open wikipedia" in hay or "open the belgrade page" in hay:
        return [
            scripted_progress("launching Chromium"),
            scripted_delay(1.2),
            scripted_tool("send_message", text="Opening Chromium on the Pi desktop."),
            scripted_tool("open_path", path="https://en.wikipedia.org/wiki/Belgrade"),
            scripted_delay(2.8),
            scripted_tool(
                "send_message",
                text="Wikipedia is on this computer. Open the screen to watch or take control.",
            ),
            scripted_finish("Wikipedia is on this computer. Open the screen to watch or take control."),
        ]
    if "attractions, weather" in hay or "in parallel" in hay or "three workers" in hay:
        return [
            scripted_progress("working through attractions, weather, and cafes"),
            scripted_delay(2.0),
            scripted_tool(
                "send_message",
                text="Attractions: Kalemegdan, Skadarlija, and the Temple of Saint Sava.",
            ),
            scripted_delay(1.8),
            scripted_tool(
                "send_message",
                text="Weather: clear, about 22°C, light wind off the river.",
            ),
            scripted_delay(1.8),
            scripted_tool(
                "send_message",
                text="Cafes: start by the water at Beton Hala, then walk up to Skadarlija.",
            ),
            scripted_finish(""),
        ]
    if "list three attractions in belgrade" in hay:
        return [
            scripted_delay(0.8),
            scripted_finish("Kalemegdan, Skadarlija, and the Temple of Saint Sava."),
        ]
    if "current weather notes for belgrade" in hay:
        return [
            scripted_delay(1.1),
            scripted_finish("Clear, about 22°C. Light wind off the river."),
        ]
    if "cafe recommendations in belgrade" in hay:
        return [
            scripted_delay(1.4),
            scripted_finish("Start with a riverside spot near Beton Hala, then Skadarlija."),
        ]
    if "e2e-consent-page" in hay:
        return [
            scripted_consent(
                action_class=CLASS_PAGE,
                scope_key="https://example.com",
                summary="Fill, type, or click on https://example.com in the remote browser?",
                detail="page_input: https://example.com",
            ),
            scripted_finish(""),
        ]
    if "e2e-consent-exec-long" in hay:
        command = (
            'ls -la "/home/artek/Изображения/Снимки экрана/'
            "edbc3632c9584b229513834046b1ab84.jpeg\" && "
            'file "/home/artek/Изображения/Снимки экрана/'
            "edbc3632c9584b229513834046b1ab84.jpeg\""
        )
        return [
            scripted_consent(
                action_class=CLASS_OWNER_EXEC,
                scope_key=OWNER_HOME_SCOPE,
                summary=f"Run `{command}` on your computer?",
                detail=f"owner_exec: {command}\ncwd: ~",
            ),
            scripted_finish(""),
        ]
    if "e2e-consent-browse" in hay:
        return [
            scripted_consent(
                action_class=CLASS_BROWSE,
                scope_key="https://example.com",
                summary="Open https://example.com on the remote desktop?",
                detail="browse: https://example.com",
            ),
            scripted_finish(""),
        ]
    if "e2e-send-file-missing" in hay:
        return [
            scripted_tool("send_file", path="missing-notes.txt"),
            scripted_finish("I could not find that file."),
        ]
    if "e2e-send-file" in hay:
        return [
            scripted_tool(
                "send_file",
                path="notes.txt",
                content="hello from the bot",
                text="Here is notes.txt",
            ),
            scripted_finish(""),
        ]
    if "e2e-slow" in text:
        return [scripted_delay(2.5), scripted_finish(E2E_SLOW_ANSWER)]
    if "e2e-markdown-preview" in text:
        return [scripted_finish(E2E_MARKDOWN_ANSWER)]
    if "e2e-fail" in text:
        return [scripted_finish(E2E_FAIL_ERROR, status="failed", error=E2E_FAIL_ERROR)]
    return [scripted_text("ok"), scripted_finish("ok")]


class ScriptedRuntime(RuntimeBase):
    def __init__(
        self,
        settings: Settings,
        store: Any | None = None,
        computers: Any | None = None,
    ) -> None:
        super().__init__(settings, store=store, computers=computers)
        self._queue: list[list[ScriptedStep]] = []
        self._seq = 0
        self.last_tool_results: list[tuple[str, dict[str, Any]]] = []

    def queue_turn(self, *steps: ScriptedStep) -> None:
        self._queue.append(list(steps))

    async def start(self) -> None:
        self._ensure_dirs()
        saved = self._load_state()
        live = await self.ensure_session(saved, name="artek-buddy")
        self.default_agent_id = live
        self._save_state(live)
        log.info("scripted runtime ready default_agent=%s", live)

    async def create_session(
        self,
        name: str = "artek-buddy",
        persist_default: bool = False,
        bot_id: str | None = None,
        role: str = "lead",
    ) -> str:
        self._seq += 1
        agent_id = f"sa-{self._seq}"
        self._agents[agent_id] = {"name": name, "role": role}
        self.bind_agent_bot(agent_id, bot_id)
        if persist_default or self.default_agent_id is None:
            self.default_agent_id = agent_id
            self._save_state(agent_id)
        log.info("created scripted agent %s", agent_id)
        return agent_id

    async def ensure_session(
        self,
        agent_id: str | None,
        name: str = "artek-buddy",
        bot_id: str | None = None,
        role: str = "lead",
    ) -> str:
        if agent_id and agent_id in self._agents:
            self.bind_agent_bot(agent_id, bot_id)
            return agent_id
        if agent_id:
            self._agents[agent_id] = {"name": name, "role": role}
            self.bind_agent_bot(agent_id, bot_id)
            if self.default_agent_id is None:
                self.default_agent_id = agent_id
                self._save_state(agent_id)
            return agent_id
        if self.default_agent_id:
            return await self.ensure_session(
                self.default_agent_id,
                name=name,
                bot_id=bot_id,
                role=role,
            )
        return await self.create_session(
            name=name,
            persist_default=self.default_agent_id is None,
            bot_id=bot_id,
            role=role,
        )

    async def stream(
        self,
        prompt: str,
        session_id: str | None = None,
        bot_id: str | None = None,
        role: str = "lead",
    ) -> AsyncIterator[ProductStreamEvent | RunRecord]:
        agent_id = await self.ensure_session(session_id, bot_id=bot_id, role=role)
        self.bind_agent_bot(agent_id, bot_id)
        steps = self._queue.pop(0) if self._queue else steps_for_prompt(prompt)
        tools = ProductTools(self)
        result = ""
        status = "completed"
        error: str | None = None
        run_id = new_id("run")
        for step in steps:
            if step.delay_s:
                await asyncio.sleep(step.delay_s)
                continue
            if step.raise_error:
                raise AgentRuntimeError(step.raise_error)
            if step.consent:
                hub = getattr(self, "consent", None)
                if hub is not None:
                    ctx_bot, ctx_run, _thread = self.resolve_turn_context(bot_id)
                    hub.offer(
                        bot_id=ctx_bot or bot_id or "",
                        action_class=str(step.consent.get("action_class") or ""),
                        scope_key=str(step.consent.get("scope_key") or "*"),
                        summary=str(step.consent.get("summary") or "Allow this?"),
                        run_id=ctx_run,
                        detail=step.consent.get("detail"),
                    )
                continue
            if step.blocks:
                posted = tools._append_bot_blocks(
                    {},
                    bot_id,
                    _bind_block_values(step.blocks, bot_id),
                )
                if not posted.get("ok"):
                    raise AgentRuntimeError(str(posted.get("error") or "could not append blocks"))
                continue
            if step.tool:
                tool_result = tools.execute(step.tool, step.args, bound_bot_id=bot_id)
                self.last_tool_results.append((step.tool, tool_result))
                for typ, payload in _map_tool_to_events(step.tool, step.tool, step.args, "completed"):
                    yield ProductStreamEvent(type=typ, payload=payload)
                continue
            if step.event:
                yield ProductStreamEvent(type=step.event[0], payload=step.event[1])
                if step.event[0] == "thread.message.updated":
                    text = str(step.event[1].get("text") or "")
                    if text:
                        result = text
                continue
            if step.status or step.result is not None:
                status = step.status or "completed"
                result = step.result if step.result is not None else result
                error = step.error
        yield RunRecord(
            id=run_id,
            agent_id=agent_id,
            status=status,
            result=result or None,
            error=error,
        )

    async def list_models(self) -> list[dict[str, Any]]:
        model_id = self.settings.cursor_model or "scripted"
        return [{"id": model_id}]
