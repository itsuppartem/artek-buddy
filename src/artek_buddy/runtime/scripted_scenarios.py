"""Scripted E2E prompts and step lists. Runtime plumbing stays on ScriptedRuntime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from artek_buddy.bot_asks import ASK_REPLY_MARK, ASKED_YOU_MARK
from artek_buddy.consent import (
    CLASS_BROWSE,
    CLASS_OWNER_EXEC,
    CLASS_OWNER_READ,
    CLASS_OWNER_WRITE,
    CLASS_PAGE,
    OWNER_HOME_SCOPE,
    browse_origin,
)

E2E_DRAFT_LEAK = "grade's current weather from a public API"
E2E_DRAFT_ANSWER = "Belgrade is 22°C and clear."
E2E_CLOSE_STATUS = "Closing Chromium"
E2E_SLOW_ANSWER = "slow done"
E2E_LATE_COMPLETE = "pong"
E2E_MARKDOWN_ANSWER = "**Belgrade** weather is 22C. [Open docs](https://example.com/artek-buddy)"
E2E_ASK_QUESTION = "Which city?"
E2E_ASK_FREE_QUESTION = "What should I call you?"
E2E_OWNER_HELP_QUESTION = "I cannot continue in the browser. Please complete the blocked step."
E2E_OWNER_HELP_ANSWER = "I continued after your help."
E2E_FAIL_ERROR = "scripted fail"
E2E_FAIL_RAW_ERROR = "run failed: run-fb7fd73f-32ed-43ed-a22f-a561aab1600a"
E2E_META_TEXT = "Remembered: Prefers short answers without emoji"
E2E_PROGRESS_TEXT = "Checking the desktop"
E2E_CARD_KEY = "City"
E2E_CARD_VALUE = "Belgrade"
E2E_COMPUTER_TEXT = "Opened Chromium"
E2E_CHILD_NAME = "Spawned pal"
E2E_CHILD_ARCHIVED = "Old pal"
E2E_SUBAGENT_NAME = "Researcher"
E2E_SUBAGENT_TASK = "please e2e-slow now"
E2E_WORKER_ACK = "Working in the background."
E2E_WORKER_STATUS = "Still working."
E2E_WORKER_STEER_ACK = "Got it. I'll apply that next."
E2E_GIT_APPROVAL = "Always ask before a git commit, a new branch, a pull request or MR, or a merge."
E2E_GIT_MR = "Wait for MR approval."
E2E_GIT_BAN = "Don't merge until I say so."
E2E_GIT_FREE = "You may merge and push without asking."
E2E_WORKER_SUMMARY = "The background job is done."
E2E_WORKER_RESULT = "blocked work finished"
E2E_WORKER_BLOCK_S = 10.0
E2E_WORKER_ACTIVITY_TOOLS = 20
E2E_WORKER_ACTIVITY_HOLD_S = 8.0
E2E_WORKER_PROGRESS_STEP = "commit"
E2E_WORKER_PROGRESS_REMAINING = "push MR 76"
E2E_WORKER_PROGRESS_STEP_2 = "push MR 76"
E2E_WORKER_PROGRESS_REMAINING_2 = "comment on the ticket"
E2E_WORKER_PROGRESS_LINE = "Still working: commit. Next: push MR 76."
E2E_WORKER_PROGRESS_LINE_2 = "Still working: push MR 76. Next: comment on the ticket."
E2E_WORKER_PROGRESS_RESULT = "progress job done"
E2E_WORKER_PROGRESS_HOLD_S = 8.0
E2E_WORKER_PROGRESS_GAP_S = 0.4
E2E_LEAD_OWNER_SSH = "Lead must not hold This-PC SSH."
E2E_ASK_READY = "I am ready to answer. The city is Subotica."
E2E_ASK_ANSWER = "They said the city is Subotica."
E2E_OLDER_PREFIX = "e2e-old-"
E2E_OLDER_COUNT = 51
E2E_HANG_S = 12.0
E2E_ASK_DETAIL = "I can open Wikipedia on the desktop after you pick one."
E2E_TAKEOVER_REASON = "Pass the site check, then Release."
E2E_GENERATE_ERROR = "could not generate that image"
E2E_SEND_TEASER = "Working on the spec."
E2E_SEND_ANSWER = "The specification is ready."
E2E_AUTH_ERROR = "Authentication error If you are logged in, try logging out and back in."
E2E_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
E2E_BOOK_URL = ""


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
    ignore_cancel: bool = False
    write_home: tuple[str, bytes] | None = None
    owner_auto_path: str | None = None


def scripted_consent(
    *,
    action_class: str,
    scope_key: str,
    summary: str,
    detail: str | None = None,
    path: str | None = None,
    job: dict[str, Any] | None = None,
) -> ScriptedStep:
    return ScriptedStep(
        consent={
            "action_class": action_class,
            "scope_key": scope_key,
            "summary": summary,
            "detail": detail,
            "path": path,
            "job": job,
        }
    )


def scripted_text(text: str) -> ScriptedStep:
    return ScriptedStep(
        event=("thread.message.updated", {"text": text, "kind": "text", "replace": True})
    )


def scripted_progress(text: str, kind: str = "thinking") -> ScriptedStep:
    return ScriptedStep(event=("thread.progress", {"text": text, "kind": kind, "replace": True}))


def scripted_tool(tool: str, **args: Any) -> ScriptedStep:
    return ScriptedStep(tool=tool, args=dict(args))


def scripted_delay(seconds: float, *, ignore_cancel: bool = False) -> ScriptedStep:
    return ScriptedStep(delay_s=seconds, ignore_cancel=ignore_cancel)


def scripted_finish(
    result: str = "ok", status: str = "completed", error: str | None = None
) -> ScriptedStep:
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


def _materialize_blocks(
    store: Any, blocks: list[dict[str, Any]], parent_bot_id: str | None
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in blocks:
        block = dict(raw)
        if block.get("kind") == "child_bot" and block.get("bot_id") == "$new" and store is not None:
            child = store.create_bot(
                name=str(block.get("name") or "Child"),
                title=str(block.get("title") or ""),
            )
            block["bot_id"] = child.id
            block["status"] = "created"
        out.append(_bind_block_values(block, parent_bot_id))
    return out


def _user_tail(prompt: str) -> str:
    """Last wrap_turn_prompt segment is the user (or worker) text."""
    return (prompt or "").rsplit("\n\n", 1)[-1]


def _parse_ask_bot(user: str) -> tuple[str, str] | None:
    key = "e2e-ask-bot "
    idx = user.lower().find(key)
    if idx < 0:
        return None
    rest = user[idx + len(key) :]
    if " | " not in rest:
        return None
    name, question = rest.split(" | ", 1)
    name = name.strip()
    question = question.strip()
    if not name or not question:
        return None
    return name, question


def _parse_identity_city(user: str) -> str | None:
    key = "e2e-identity-city "
    idx = user.lower().find(key)
    if idx < 0:
        return None
    rest = user[idx + len(key) :].strip()
    if not rest:
        return None
    token = rest.split()[0].strip(".,;:!?")
    return token or None


def steps_for_prompt(prompt: str) -> list[ScriptedStep]:
    user = _user_tail(prompt or "")
    hay = user.lower()
    if ASKED_YOU_MARK in hay:
        return [
            scripted_tool("send_message", text=E2E_ASK_READY),
            scripted_finish(""),
        ]
    if ASK_REPLY_MARK in hay:
        return [scripted_finish(E2E_ASK_ANSWER)]
    parsed_ask = _parse_ask_bot(user)
    if parsed_ask is not None:
        dest_name, question = parsed_ask
        return [
            scripted_tool("message_bot", bot=dest_name, text=question),
            scripted_finish("I asked them."),
        ]
    if "e2e-plugin-docs" in hay or "please use docs" in hay:
        return [scripted_tool("docs_read"), scripted_finish("")]
    if "e2e-list-apps" in hay:
        return [
            scripted_tool("list_apps", q="docs"),
            scripted_finish("I'll search apps."),
        ]
    if "e2e-connect-docs" in hay:
        return [
            scripted_tool("connect_app", slug="docs"),
            scripted_finish("I'll attach Docs."),
        ]
    if "e2e-connect-mail" in hay:
        return [
            scripted_tool("connect_app", slug="mail"),
            scripted_finish("I'll attach Mail."),
        ]
    if "e2e-connect-nope" in hay:
        return [
            scripted_tool("connect_app", slug="nope"),
            scripted_finish("I could not attach that."),
        ]
    if "e2e-install-book" in hay:
        url = E2E_BOOK_URL or "http://127.0.0.1/SKILL.md"
        origin = browse_origin(url) or "http://127.0.0.1"
        return [
            scripted_consent(
                action_class=CLASS_BROWSE,
                scope_key=origin,
                summary=f"Install a skill from {origin}?",
                detail=f"browse: {origin}",
            ),
            scripted_tool("install_book", url=url),
            scripted_finish("I'll keep that skill."),
        ]
    if "e2e-forget-book" in hay:
        return [
            scripted_tool("forget_book", name="Invoice"),
            scripted_finish("Forgotten."),
        ]
    if "e2e-run-book" in hay or "please run invoice" in hay:
        return [
            scripted_tool("open_book", name="Invoice"),
            scripted_finish("Following Invoice."),
        ]
    if "e2e-hide-draft" in hay:
        return [
            scripted_progress("planning the lookup"),
            scripted_text(E2E_DRAFT_LEAK),
            scripted_delay(0.6),
            scripted_finish(E2E_DRAFT_ANSWER),
        ]
    if "e2e-close-browser" in hay:
        return [
            scripted_tool("send_message", text=E2E_CLOSE_STATUS),
            scripted_tool("close_app", application="chromium"),
            scripted_finish("browser closed"),
        ]
    city = _parse_identity_city(user)
    if city is not None:
        return [
            scripted_tool(
                "remember",
                content=f"Lives in {city}",
                kind="place",
                section="identity",
            ),
            scripted_finish("I'll remember that."),
        ]
    if "e2e-remember-git-free" in hay:
        return [
            scripted_tool(
                "remember",
                content=E2E_GIT_FREE,
                kind="rule",
                section="bans",
            ),
            scripted_finish("I'll remember that."),
        ]
    if "e2e-remember-git-approval" in hay:
        return [
            scripted_tool(
                "remember",
                content=E2E_GIT_APPROVAL,
                kind="rule",
                section="wait",
            ),
            scripted_tool(
                "remember",
                content=E2E_GIT_MR,
                kind="rule",
                section="wait",
            ),
            scripted_tool(
                "remember",
                content=E2E_GIT_BAN,
                kind="rule",
                section="bans",
            ),
            scripted_finish("I'll remember that."),
        ]
    if "e2e-remember-same-thrice" in hay:
        rule = "There is no YouTrack API token. Do not search for one or call YouTrack REST."
        return [
            scripted_tool("remember", content=rule, kind="rule", section="do_not"),
            scripted_tool("remember", content=rule, kind="rule", section="do_not"),
            scripted_tool(
                "remember",
                content=rule + " Commenting needs the already-logged-in Chromium issue tab.",
                kind="rule",
                section="do_not",
            ),
            scripted_finish("I'll remember that."),
        ]
    if "e2e-worker-auto-read" in hay:
        return [
            scripted_tool(
                "spawn_subagent",
                name="WorkerAutoRead",
                task="please e2e-consent-auto-read",
            ),
            scripted_finish(E2E_WORKER_ACK),
        ]
    if "e2e-background-worker-remember" in hay:
        return [
            scripted_tool(
                "spawn_subagent",
                name=E2E_SUBAGENT_NAME,
                task="please e2e-worker-remember-rule",
            ),
            scripted_finish(E2E_WORKER_ACK),
        ]
    if "e2e-worker-remember-rule" in hay:
        return [
            scripted_tool(
                "remember",
                content=(
                    "There is no YouTrack API token. Do not search for one or call YouTrack REST."
                ),
                kind="rule",
                section="do_not",
            ),
            scripted_finish("rule stored"),
        ]
    if "e2e-remember-twice" in hay:
        return [
            scripted_tool(
                "remember",
                content=(
                    "Do not ask the owner for permission to work on this bot's computer or "
                    "browser, or to run read-only commands on the owner's paired PC. "
                    "Do not prompt."
                ),
                kind="rule",
                section="bans",
            ),
            scripted_tool(
                "remember",
                content="Don't ask for read permission",
                kind="preference",
            ),
            scripted_finish("I'll remember that."),
        ]
    if "e2e-remember" in hay:
        return [
            scripted_tool(
                "remember",
                content="Prefers short answers without emoji",
                kind="preference",
                section="tone",
            ),
            scripted_finish("I'll remember that."),
        ]
    if "e2e-thread-blocks" in hay:
        return [
            scripted_blocks(
                {"kind": "meta", "text": E2E_META_TEXT},
                {"kind": "progress", "text": E2E_PROGRESS_TEXT},
                {"kind": "card", "lines": [{"k": E2E_CARD_KEY, "v": E2E_CARD_VALUE}]},
                {"kind": "text", "text": "Working on the desktop."},
                {"kind": "computer", "state": "done", "text": E2E_COMPUTER_TEXT},
                {
                    "kind": "child_bot",
                    "bot_id": "$new",
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
            scripted_finish("ok"),
        ]
    if "e2e-ask-free" in hay:
        return [
            scripted_tool("ask_user", question=E2E_ASK_FREE_QUESTION),
            scripted_finish(E2E_OWNER_HELP_ANSWER),
        ]
    if "e2e-ask" in hay:
        return [
            scripted_tool(
                "ask_user",
                question=E2E_ASK_QUESTION,
                options=["Belgrade", "Berlin"],
                detail=E2E_ASK_DETAIL,
            ),
            scripted_finish(E2E_OWNER_HELP_ANSWER),
        ]
    if "e2e-lead-owner-ssh" in hay:
        return [
            scripted_tool("run_owner_command", command="sleep 120"),
            scripted_finish(E2E_LEAD_OWNER_SSH),
        ]
    if "e2e-blocked-browser" in hay:
        return [
            scripted_tool(
                "ask_user",
                question=E2E_OWNER_HELP_QUESTION,
                options=["I completed the step", "Stop"],
            ),
            scripted_finish(E2E_OWNER_HELP_ANSWER),
        ]
    if "a background worker finished" in hay:
        return [scripted_finish(E2E_WORKER_SUMMARY)]
    if "e2e-worker-activity-no-text" in hay:
        return [
            scripted_tool(
                "spawn_subagent",
                name=E2E_SUBAGENT_NAME,
                task="please e2e-worker-tools-no-text",
            ),
            scripted_finish(E2E_WORKER_ACK),
        ]
    if "e2e-worker-tools-no-text" in hay:
        return [
            *[scripted_tool("list_subagents") for _ in range(E2E_WORKER_ACTIVITY_TOOLS)],
            scripted_delay(E2E_WORKER_ACTIVITY_HOLD_S),
            scripted_finish("tools without text finished"),
        ]
    if "e2e-worker-false-idle" in hay:
        return [
            scripted_tool("inspect_subagent", ref=E2E_SUBAGENT_NAME),
            scripted_tool("stop_subagent", ref=E2E_SUBAGENT_NAME),
            scripted_finish(E2E_WORKER_STATUS),
        ]
    if "e2e-worker-stale-stop" in hay:
        return [
            scripted_tool("inspect_subagent", ref=E2E_SUBAGENT_NAME),
            scripted_tool(
                "stop_subagent",
                ref=E2E_SUBAGENT_NAME,
                inspected_activity_seq=0,
            ),
            scripted_finish(E2E_WORKER_STATUS),
        ]
    if "e2e-background-worker-chat" in hay:
        return [
            scripted_tool(
                "spawn_subagent",
                name=E2E_SUBAGENT_NAME,
                task="please e2e-worker-block",
            ),
            scripted_finish(E2E_WORKER_ACK),
        ]
    if "e2e-worker-progress-run" in hay:
        return [
            scripted_tool(
                "report_progress",
                step=E2E_WORKER_PROGRESS_STEP,
                remaining=E2E_WORKER_PROGRESS_REMAINING,
            ),
            scripted_tool(
                "report_progress",
                step=E2E_WORKER_PROGRESS_STEP,
                remaining=E2E_WORKER_PROGRESS_REMAINING,
            ),
            scripted_delay(E2E_WORKER_PROGRESS_GAP_S),
            scripted_tool(
                "report_progress",
                step=E2E_WORKER_PROGRESS_STEP_2,
                remaining=E2E_WORKER_PROGRESS_REMAINING_2,
            ),
            scripted_delay(E2E_WORKER_PROGRESS_HOLD_S),
            scripted_finish(E2E_WORKER_PROGRESS_RESULT),
        ]
    if "e2e-worker-progress" in hay:
        return [
            scripted_tool(
                "spawn_subagent",
                name="WorkerProgress",
                task="please e2e-worker-progress-run",
            ),
            scripted_finish(E2E_WORKER_ACK),
        ]
    if "e2e-worker-status" in hay:
        return [
            scripted_tool("send_message", text=E2E_WORKER_STATUS),
            scripted_tool("inspect_subagent", ref=E2E_SUBAGENT_NAME),
            scripted_finish(E2E_WORKER_STATUS),
        ]
    if "e2e-worker-steer" in hay:
        return [
            scripted_tool(
                "steer_subagent",
                ref=E2E_SUBAGENT_NAME,
                text="use path B",
            ),
            scripted_finish(E2E_WORKER_STEER_ACK),
        ]
    if "e2e-worker-block" in hay:
        return [
            scripted_tool("list_subagents"),
            scripted_delay(E2E_WORKER_BLOCK_S),
            scripted_tool("list_subagents"),
            scripted_finish(E2E_WORKER_RESULT),
        ]
    if "e2e-subagent-hang" in hay:
        return [
            scripted_tool(
                "spawn_subagent",
                name=E2E_SUBAGENT_NAME,
                task="please e2e-hang now",
            ),
            scripted_delay(E2E_HANG_S),
            scripted_finish("worker started"),
        ]
    if "e2e-subagent" in hay:
        return [
            scripted_tool(
                "spawn_subagent",
                name=E2E_SUBAGENT_NAME,
                task=E2E_SUBAGENT_TASK,
            ),
            scripted_finish("worker started"),
        ]
    if "the owner released the desktop" in hay:
        return [scripted_finish("continuing after takeover")]
    if "e2e-park-takeover" in hay or "e2e-takeover" in hay:
        return [
            scripted_tool("request_takeover", reason=E2E_TAKEOVER_REASON),
            scripted_delay(E2E_HANG_S),
            scripted_finish("should not finish"),
        ]
    if "e2e-load-earlier" in hay:
        return [
            *(
                scripted_blocks({"kind": "text", "text": f"{E2E_OLDER_PREFIX}{index:02d}"})
                for index in range(E2E_OLDER_COUNT)
            ),
            scripted_finish(""),
        ]
    if "e2e-hang" in hay:
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
    if "e2e-wake-computer" in hay:
        return [
            scripted_progress("opening the desktop"),
            scripted_consent(
                action_class=CLASS_BROWSE,
                scope_key="https://en.wikipedia.org",
                summary="Open https://en.wikipedia.org on the remote desktop?",
                detail="browse: https://en.wikipedia.org",
            ),
            scripted_tool("open_path", path="https://en.wikipedia.org/wiki/Belgrade"),
            scripted_delay(E2E_HANG_S),
            scripted_finish("The desktop is up."),
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
            scripted_finish(
                "Wikipedia is on this computer. Open the screen to watch or take control."
            ),
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
            'edbc3632c9584b229513834046b1ab84.jpeg" && '
            'file "/home/artek/Изображения/Снимки экрана/'
            'edbc3632c9584b229513834046b1ab84.jpeg"'
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
    if "e2e-consent-read-escape" in hay:
        return [
            scripted_consent(
                action_class=CLASS_OWNER_READ,
                scope_key=OWNER_HOME_SCOPE,
                summary="Read /etc/passwd from your computer?",
                detail="owner_read: /etc/passwd",
                path="/etc/passwd",
                job={"kind": "read", "path": "/etc/passwd"},
            ),
            scripted_finish(""),
        ]
    if "e2e-consent-read" in hay:
        return [
            scripted_consent(
                action_class=CLASS_OWNER_READ,
                scope_key=OWNER_HOME_SCOPE,
                summary="Read notes.txt from your computer?",
                detail="owner_read: notes.txt",
                path="notes.txt",
                job={"kind": "read", "path": "notes.txt"},
            ),
            scripted_finish(""),
        ]
    if "e2e-consent-write" in hay:
        return [
            scripted_consent(
                action_class=CLASS_OWNER_WRITE,
                scope_key=OWNER_HOME_SCOPE,
                summary="Write ci-out.txt on your computer?",
                detail="owner_write: ci-out.txt",
                path="ci-out.txt",
                job={"kind": "write", "path": "ci-out.txt", "text": "ci wrote this\n"},
            ),
            scripted_finish(""),
        ]
    if "e2e-consent-list" in hay:
        return [
            scripted_consent(
                action_class=CLASS_OWNER_READ,
                scope_key=OWNER_HOME_SCOPE,
                summary="List ~ on your computer?",
                detail="owner_list: ~",
                path="~",
                job={"kind": "list", "path": "~"},
            ),
            scripted_finish(""),
        ]
    if "e2e-consent-auto-read" in hay:
        return [
            ScriptedStep(owner_auto_path="notes.txt"),
            scripted_finish("got notes"),
        ]
    if "e2e-send-then-repeat" in hay:
        return [
            scripted_tool("send_message", text=E2E_SEND_TEASER),
            scripted_finish(E2E_SEND_TEASER),
        ]
    if "e2e-send-then-answer" in hay:
        return [
            scripted_tool("send_message", text=E2E_SEND_TEASER),
            scripted_finish(E2E_SEND_ANSWER),
        ]
    if "e2e-generate-image-fail" in hay:
        return [
            scripted_tool("send_message", text="Generating…"),
            scripted_delay(0.2),
            scripted_finish(E2E_GENERATE_ERROR, status="failed", error=E2E_GENERATE_ERROR),
        ]
    if "e2e-generate-image" in hay:
        return [
            scripted_tool("send_message", text="Generating…"),
            scripted_delay(2.5),
            ScriptedStep(write_home=("fox.png", E2E_PNG)),
            scripted_tool("send_file", path="fox.png", name="fox.png"),
            scripted_finish(""),
        ]
    if "e2e-send-image" in hay:
        return [
            ScriptedStep(write_home=("shot.png", E2E_PNG)),
            scripted_tool("send_file", path="shot.png", name="shot.png", text="Here is shot.png"),
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
    if "e2e-late-complete" in hay:
        return [
            scripted_delay(2.5, ignore_cancel=True),
            scripted_text(E2E_LATE_COMPLETE),
            scripted_finish(E2E_LATE_COMPLETE),
        ]
    if "e2e-slow" in hay:
        return [scripted_delay(2.5), scripted_finish(E2E_SLOW_ANSWER)]
    if "e2e-markdown-preview" in hay:
        return [scripted_finish(E2E_MARKDOWN_ANSWER)]
    if "e2e-fail-raw" in hay:
        return [scripted_finish("", status="failed", error=E2E_FAIL_RAW_ERROR)]
    if "e2e-fail-slow" in hay:
        return [
            scripted_delay(2.5),
            scripted_finish(E2E_FAIL_ERROR, status="failed", error=E2E_FAIL_ERROR),
        ]
    if "e2e-fail" in hay:
        return [scripted_finish(E2E_FAIL_ERROR, status="failed", error=E2E_FAIL_ERROR)]
    return [scripted_text("ok"), scripted_finish("ok")]
