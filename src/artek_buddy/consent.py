from __future__ import annotations

import logging
import re
import shlex
import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from artek_buddy.contracts.events import ProductEvent, ProductEventType
from artek_buddy.db.shaping import isoformat_utc, new_id

log = logging.getLogger("artek_buddy")

DECISIONS = ("once", "always", "deny")
LABELS = {"once": "Allow once", "always": "Always", "deny": "Deny"}
WAIT_SECONDS = 300
OWNER_FILE_WAIT = 90
OWNER_RESULT_WAIT = 120
CLASS_BROWSE = "browse"
CLASS_INPUT = "desktop_input"
CLASS_PAGE = "page_input"
CLASS_OWNER_READ = "owner_read"
CLASS_OWNER_WRITE = "owner_write"
CLASS_OWNER_EXEC = "owner_exec"
OWNER_CLASSES = {CLASS_OWNER_READ, CLASS_OWNER_WRITE, CLASS_OWNER_EXEC}
OWNER_HOME_SCOPE = "~"

_READONLY_COMMANDS = frozenset(
    {
        "ls",
        "dir",
        "cat",
        "tac",
        "echo",
        "printf",
        "pwd",
        "head",
        "tail",
        "grep",
        "egrep",
        "fgrep",
        "rg",
        "find",
        "wc",
        "which",
        "whereis",
        "type",
        "diff",
        "stat",
        "du",
        "df",
        "file",
        "uname",
        "whoami",
        "id",
        "hostname",
        "date",
        "uptime",
        "env",
        "printenv",
        "locale",
        "realpath",
        "readlink",
        "basename",
        "dirname",
        "tree",
        "true",
        "false",
        "test",
        "[",
        "cd",
        "sleep",
    }
)
_READONLY_WRAPPERS = frozenset({"timeout", "nice", "nohup", "command", "ionice", "stdbuf", "time"})
_GIT_READONLY = frozenset(
    {"status", "log", "diff", "show", "branch", "rev-parse", "ls-files", "blame", "describe", "rev-list"}
)
_FIND_WRITE_FLAGS = frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir"})
_SAFE_SUBST = re.compile(
    r"(?:\$\(|`)(pwd|whoami|id|hostname|date|uname)(?:\s+[^)`]*)?(?:\)|`)"
)


def decision_from_label(value: str) -> str | None:
    raw = (value or "").strip().lower()
    if raw in DECISIONS:
        return raw
    if raw in {"allow once", "once", "this time"}:
        return "once"
    if raw in {"always", "allow always"}:
        return "always"
    if raw in {"deny", "decline", "no"}:
        return "deny"
    return None


def browse_origin(value: str) -> str | None:
    text = (value or "").strip()
    if not text or not re.match(r"(?i)^(https?://|www\.)", text):
        return None
    raw = text if "://" in text else f"https://{text}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    scheme = (parsed.scheme or "https").lower()
    return f"{scheme}://{host}"


def owner_scope(path: str) -> str:
    text = (path or "").strip()
    if not text:
        return ""
    parent = text.rsplit("/", 1)[0] if "/" in text.rstrip("/") else text
    return parent or text


def owner_command_is_readonly(command: str) -> bool:
    """True for explore-only shell, like Claude Code's built-in ls/cat/echo set."""
    text = (command or "").strip()
    if not text or len(text) > 4000:
        return False
    scanned = _SAFE_SUBST.sub("ok", text)
    if re.search(r"`|\$\(|\btee\b", scanned) or ">" in scanned or "<" in scanned:
        return False
    try:
        parts = [part.strip() for part in re.split(r"\s*(?:&&|\|\||[;\n|])\s*", text) if part.strip()]
    except re.error:
        return False
    if not parts:
        return False
    for part in parts:
        if not _readonly_segment(part):
            return False
    return True


def _readonly_segment(part: str) -> bool:
    try:
        tokens = shlex.split(part, posix=True)
    except ValueError:
        return False
    if not tokens:
        return False
    i = 0
    while i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i]):
        i += 1
    while i < len(tokens):
        name = tokens[i].rsplit("/", 1)[-1]
        if name == "env" and i + 1 < len(tokens):
            i += 1
            while i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i]):
                i += 1
            continue
        if name in _READONLY_WRAPPERS:
            i += 1
            while i < len(tokens) and (
                tokens[i].startswith("-") or re.match(r"^[0-9.]+[smh]?$", tokens[i])
            ):
                i += 1
            continue
        break
    rest = tokens[i:]
    if not rest:
        return True
    name = rest[0].rsplit("/", 1)[-1]
    if name == "git":
        flags = {item for item in rest[1:] if item.startswith("-")}
        sub = next((item for item in rest[1:] if not item.startswith("-")), "")
        if sub not in _GIT_READONLY:
            return False
        if sub == "branch" and flags & {"-d", "-D", "--delete"}:
            return False
        return True
    if name == "find" and any(item in _FIND_WRITE_FLAGS for item in rest[1:]):
        return False
    return name in _READONLY_COMMANDS


@dataclass
class ConsentRequest:
    id: str
    bot_id: str
    action_class: str
    scope_key: str
    summary: str
    status: str = "pending"
    run_id: str | None = None
    message_id: str | None = None


class ConsentHub:
    """Ask before changing the owner PC or leaving the Pi box. Reads do not prompt."""

    def __init__(self, store: Any, events: Any | None = None, settings: Any | None = None, auto: str | None = None) -> None:
        self.store = store
        self.events = events
        self.settings = settings
        self.auto = auto
        self.last_request_id: str | None = None
        self._lock = threading.Lock()
        self._waiters: dict[str, threading.Event] = {}
        self._decisions: dict[str, str] = {}
        self._files: dict[str, tuple[str, bytes]] = {}
        self._file_waiters: dict[str, threading.Event] = {}
        self._jobs: dict[str, dict[str, Any]] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._result_waiters: dict[str, threading.Event] = {}

    def _mode(self) -> str | None:
        if self.auto in {"allow", "deny"}:
            return self.auto
        configured = str(getattr(self.settings, "consent_auto", "") or "").strip().lower()
        if configured in {"allow", "deny"}:
            return configured
        if configured == "ask":
            return None
        if str(getattr(self.settings, "agent_runtime", "") or "") == "scripted":
            return "allow"
        return None

    def has_grant(self, bot_id: str, action_class: str, scope_key: str, device_id: str | None) -> bool:
        return self.store.find_consent_grant(bot_id, action_class, scope_key, device_id) is not None

    def offer(
        self,
        *,
        bot_id: str,
        action_class: str,
        scope_key: str,
        summary: str,
        run_id: str | None,
        device_id: str | None = None,
        detail: str | None = None,
        path: str | None = None,
        job: dict[str, Any] | None = None,
    ) -> str | None:
        """Post Allow once / Always / Deny and return the request id. Does not wait."""
        del device_id
        bot = self.store.get_bot(bot_id)
        if bot is None:
            return None
        key = (scope_key or "*").strip() or "*"
        request_id = new_id("cns")
        self.last_request_id = request_id
        if job:
            self._jobs[request_id] = {**job, "action_class": action_class, "scope_key": key}
        blocks = [
            {
                "kind": "ask",
                "text": summary,
                "detail": detail or f"{action_class}: {key}",
                "status": "pending",
                "consent_id": request_id,
                "actions": [
                    {"id": "once", "label": "Allow once"},
                    {"id": "always", "label": "Always"},
                    {"id": "deny", "label": "Deny"},
                ],
            }
        ]
        message = self.store.append_bot_message(bot, blocks, run_id=run_id)
        self.store.create_consent_request(
            request_id,
            bot_id=bot_id,
            run_id=run_id,
            thread_id=bot.thread_id,
            message_id=message.id,
            action_class=action_class,
            scope_key=key,
            summary=summary,
            workspace_id=bot.workspace_id,
        )
        waiter = threading.Event()
        with self._lock:
            self._waiters[request_id] = waiter
        if run_id:
            try:
                self.store.mark_run_waiting_input(run_id)
            except Exception:
                log.exception("failed to mark waiting_input")
        self._publish(
            bot,
            ProductEventType.THREAD_MESSAGE_CREATED,
            {"message": message.model_dump(mode="json")},
            run_id,
        )
        waiting: dict[str, Any] = {
            "run_id": run_id,
            "consent_id": request_id,
            "text": summary,
            "action_class": action_class,
            "scope_key": key,
        }
        if path:
            waiting["path"] = path
        if job:
            for field in ("command", "cwd", "kind"):
                if job.get(field):
                    waiting[field] = job[field]
        self._publish(
            bot,
            ProductEventType.RUN_WAITING_INPUT,
            waiting,
            run_id,
        )
        return request_id

    def require(
        self,
        *,
        bot_id: str,
        action_class: str,
        scope_key: str,
        summary: str,
        run_id: str | None,
        device_id: str | None,
        detail: str | None = None,
        path: str | None = None,
        job: dict[str, Any] | None = None,
    ) -> bool:
        self.last_request_id = None
        if action_class == CLASS_OWNER_READ:
            return True
        key = (scope_key or "*").strip() or "*"
        if self.has_grant(bot_id, action_class, key, device_id):
            return True
        mode = self._mode()
        if mode == "allow":
            return True
        if mode == "deny":
            return False
        request_id = self.offer(
            bot_id=bot_id,
            action_class=action_class,
            scope_key=key,
            summary=summary,
            run_id=run_id,
            device_id=device_id,
            detail=detail,
            path=path,
            job=job,
        )
        if not request_id:
            return False
        with self._lock:
            waiter = self._waiters.get(request_id)
        if waiter is not None:
            waiter.wait(WAIT_SECONDS)
        decision = self._decisions.get(request_id, "deny")
        if run_id:
            try:
                self.store.mark_run_running(run_id)
            except Exception:
                log.exception("failed to resume run after consent")
        return decision in {"once", "always"}

    def answer(self, request_id: str, decision: str, device_id: str | None) -> ConsentRequest | None:
        picked = decision_from_label(decision)
        if picked is None:
            return None
        row = self.store.answer_consent_request(request_id, picked, device_id)
        if row is None:
            return None
        if picked == "always":
            bot = self.store.get_bot(row.bot_id)
            self.store.save_consent_grant(
                bot_id=row.bot_id,
                device_id=device_id if device_id and device_id != "host" else None,
                action_class=row.action_class,
                scope_key=row.scope_key,
                workspace_id=getattr(bot, "workspace_id", None) or "ws_default",
            )
        bot = self.store.get_bot(row.bot_id)
        if bot is not None and row.message_id:
            updated = self.store.answer_message_ask(row.message_id, LABELS.get(picked, picked))
            if updated is not None:
                self._publish(
                    bot,
                    ProductEventType.THREAD_MESSAGE_CREATED,
                    {"message": updated.model_dump(mode="json")},
                    row.run_id,
                )
        with self._lock:
            self._decisions[request_id] = picked
            waiter = self._waiters.pop(request_id, None)
        if waiter is not None:
            waiter.set()
        return row

    def get_job(self, request_id: str) -> dict[str, Any] | None:
        row = self.store.get_consent_request(request_id)
        if row is None:
            return None
        job = dict(self._jobs.get(request_id) or {})
        job.setdefault("id", request_id)
        job.setdefault("action_class", row.action_class)
        job.setdefault("scope_key", row.scope_key)
        job.setdefault("summary", row.summary)
        job.setdefault("status", row.status)
        return job

    def put_owner_file(self, request_id: str, name: str, data: bytes) -> bool:
        row = self.store.get_consent_request(request_id)
        if row is None or row.action_class != CLASS_OWNER_READ:
            return False
        with self._lock:
            self._files[request_id] = (name, data)
            waiter = self._file_waiters.get(request_id)
        if waiter is not None:
            waiter.set()
        return True

    def put_owner_result(self, request_id: str, payload: dict[str, Any]) -> bool:
        row = self.store.get_consent_request(request_id)
        if row is None or row.action_class not in OWNER_CLASSES:
            return False
        with self._lock:
            self._results[request_id] = dict(payload)
            waiter = self._result_waiters.get(request_id)
        if waiter is not None:
            waiter.set()
        return True

    def take_owner_result(self, request_id: str | None) -> dict[str, Any] | None:
        if not request_id:
            return None
        waiter = threading.Event()
        with self._lock:
            if request_id in self._results:
                return self._results.pop(request_id)
            self._result_waiters[request_id] = waiter
        waiter.wait(OWNER_RESULT_WAIT)
        with self._lock:
            self._result_waiters.pop(request_id, None)
            return self._results.pop(request_id, None)

    def pull_owner_action(
        self,
        *,
        bot_id: str,
        action_class: str,
        scope_key: str,
        summary: str,
        job: dict[str, Any],
        run_id: str | None,
        device_id: str | None,
    ) -> dict[str, Any] | None:
        _ = device_id
        bot = self.store.get_bot(bot_id)
        if bot is None:
            return None
        request_id = new_id("cns")
        self.last_request_id = request_id
        self._jobs[request_id] = {**job, "action_class": action_class, "scope_key": scope_key}
        self.store.create_consent_request(
            request_id,
            bot_id=bot_id,
            run_id=run_id,
            thread_id=bot.thread_id,
            message_id=None,
            action_class=action_class,
            scope_key=scope_key,
            summary=summary,
            workspace_id=bot.workspace_id,
        )
        if run_id:
            try:
                self.store.mark_run_waiting_input(run_id)
            except Exception:
                log.exception("failed to mark waiting_input")
        payload: dict[str, Any] = {
            "run_id": run_id,
            "consent_id": request_id,
            "text": summary,
            "action_class": action_class,
            "auto": True,
        }
        for field in ("path", "command", "cwd", "kind"):
            if job.get(field):
                payload[field] = job[field]
        self._publish(bot, ProductEventType.RUN_WAITING_INPUT, payload, run_id)
        found = self.take_owner_result(request_id)
        if found is None and action_class == CLASS_OWNER_READ and job.get("kind") != "list":
            file_found = self.take_owner_file(request_id)
            if file_found is not None:
                name, data = file_found
                found = {"ok": True, "name": name, "bytes": len(data), "_data": data}
        if run_id:
            try:
                self.store.mark_run_running(run_id)
            except Exception:
                log.exception("failed to resume run after owner action")
        return found

    def pull_owner_file(
        self,
        *,
        bot_id: str,
        path: str,
        run_id: str | None,
        device_id: str | None,
    ) -> tuple[str, bytes] | None:
        """Always-grant path: no card, ask the paired client to send the file."""
        _ = device_id
        bot = self.store.get_bot(bot_id)
        if bot is None:
            return None
        request_id = new_id("cns")
        self.last_request_id = request_id
        self.store.create_consent_request(
            request_id,
            bot_id=bot_id,
            run_id=run_id,
            thread_id=bot.thread_id,
            message_id=None,
            action_class=CLASS_OWNER_READ,
            scope_key=owner_scope(path),
            summary=f"Read {path} from your computer?",
            workspace_id=bot.workspace_id,
        )
        if run_id:
            try:
                self.store.mark_run_waiting_input(run_id)
            except Exception:
                log.exception("failed to mark waiting_input")
        self._publish(
            bot,
            ProductEventType.RUN_WAITING_INPUT,
            {
                "run_id": run_id,
                "consent_id": request_id,
                "text": f"Read {path} from your computer?",
                "action_class": CLASS_OWNER_READ,
                "path": path,
                "auto": True,
            },
            run_id,
        )
        found = self.take_owner_file(request_id)
        if run_id:
            try:
                self.store.mark_run_running(run_id)
            except Exception:
                log.exception("failed to resume run after owner file")
        return found

    def take_owner_file(self, request_id: str | None) -> tuple[str, bytes] | None:
        if not request_id:
            return None
        waiter = threading.Event()
        with self._lock:
            if request_id in self._files:
                return self._files.pop(request_id)
            self._file_waiters[request_id] = waiter
        waiter.wait(OWNER_FILE_WAIT)
        with self._lock:
            self._file_waiters.pop(request_id, None)
            return self._files.pop(request_id, None)

    def _publish(self, bot: Any, event_type: ProductEventType, payload: dict[str, Any], run_id: str | None) -> None:
        if self.events is None:
            return
        try:
            self.events.publish(
                ProductEvent(
                    id=new_id("evt"),
                    workspace_id=bot.workspace_id,
                    thread_id=bot.thread_id,
                    bot_id=bot.id,
                    seq=self.events.next_seq(bot.id),
                    type=event_type,
                    created_at=isoformat_utc(),
                    payload=payload,
                    run_id=run_id,
                )
            )
        except Exception:
            log.exception("failed to publish consent event")
