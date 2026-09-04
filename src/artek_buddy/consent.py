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
OWNER_QUESTION_WAIT = 300
OWNER_FILE_WAIT = 90
OWNER_RESULT_WAIT = 120
CLASS_BROWSE = "browse"
CLASS_INPUT = "desktop_input"
CLASS_PAGE = "page_input"
CLASS_OWNER_READ = "owner_read"
CLASS_OWNER_WRITE = "owner_write"
CLASS_OWNER_EXEC = "owner_exec"
CLASS_CREDENTIAL_EXEC = "credential_exec"
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
_GIT_INSPECT_SUBS = frozenset(
    {
        "status",
        "log",
        "diff",
        "show",
        "branch",
        "rev-parse",
        "ls-files",
        "blame",
        "describe",
        "rev-list",
    }
)
_GIT_GLOBAL_INSPECT = frozenset(
    {
        "--no-pager",
        "--no-color",
        "--color",
        "--paginate",
        "--no-optional-locks",
    }
)
_GIT_REPO_OR_OUTPUT_FLAGS = frozenset(
    {
        "--output",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--config",
        "--config-env",
    }
)
_GIT_BRANCH_LIST_FLAGS = frozenset(
    {
        "--list",
        "-a",
        "--all",
        "-r",
        "--remotes",
        "-v",
        "-vv",
        "--verbose",
        "--no-color",
        "--color",
        "--show-current",
        "-q",
        "--quiet",
        "--column",
        "--no-column",
        "-i",
        "--ignore-case",
        "--abbrev",
        "--no-abbrev",
        "--merged",
        "--no-merged",
        "--contains",
        "--no-contains",
        "--points-at",
    }
)
_GIT_BRANCH_LIST_PREFIXES = ("--sort=", "--format=", "--color=", "--column=", "--abbrev=")
_FIND_INSPECT_ARITY = {
    "-print": 0,
    "-print0": 0,
    "-ls": 0,
    "-quit": 0,
    "-prune": 0,
    "-true": 0,
    "-false": 0,
    "-empty": 0,
    "-readable": 0,
    "-writable": 0,
    "-executable": 0,
    "-nouser": 0,
    "-nogroup": 0,
    "-depth": 0,
    "-xdev": 0,
    "-mount": 0,
    "-noleaf": 0,
    "-ignore_readdir_race": 0,
    "-noignore_readdir_race": 0,
    "-daystart": 0,
    "-follow": 0,
    "-L": 0,
    "-H": 0,
    "-P": 0,
    "-not": 0,
    "-or": 0,
    "-and": 0,
    "-o": 0,
    "-a": 0,
    "-help": 0,
    "-version": 0,
    "-warn": 0,
    "-nowarn": 0,
    "-name": 1,
    "-iname": 1,
    "-lname": 1,
    "-ilname": 1,
    "-path": 1,
    "-wholename": 1,
    "-ipath": 1,
    "-iwholename": 1,
    "-regex": 1,
    "-iregex": 1,
    "-regextype": 1,
    "-type": 1,
    "-xtype": 1,
    "-size": 1,
    "-user": 1,
    "-group": 1,
    "-uid": 1,
    "-gid": 1,
    "-perm": 1,
    "-mtime": 1,
    "-mmin": 1,
    "-atime": 1,
    "-amin": 1,
    "-ctime": 1,
    "-cmin": 1,
    "-used": 1,
    "-links": 1,
    "-inum": 1,
    "-samefile": 1,
    "-newer": 1,
    "-anewer": 1,
    "-cnewer": 1,
    "-maxdepth": 1,
    "-mindepth": 1,
    "-printf": 1,
    "-fstype": 1,
    "-context": 1,
}
_SAFE_SUBST = re.compile(r"(?:\$\(|`)(pwd|whoami|id|hostname|date|uname)(?:\s+[^)`]*)?(?:\)|`)")


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
    """True for explore-only shell: ls/cat/echo, inspect-only git, inspect-only find."""
    text = (command or "").strip()
    if not text or len(text) > 4000:
        return False
    scanned = _SAFE_SUBST.sub("ok", text)
    if re.search(r"`|\$\(|\btee\b", scanned) or ">" in scanned or "<" in scanned:
        return False
    try:
        parts = [
            part.strip() for part in re.split(r"\s*(?:&&|\|\||[;\n|])\s*", text) if part.strip()
        ]
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
        return _git_inspect_ok(rest)
    if name == "find":
        return _find_inspect_ok(rest)
    return name in _READONLY_COMMANDS


def _git_flag_name(item: str) -> str:
    return item.split("=", 1)[0]


def _git_repo_or_output_flag(item: str) -> bool:
    if not item.startswith("-"):
        return False
    return _git_flag_name(item) in _GIT_REPO_OR_OUTPUT_FLAGS


def _git_inspect_ok(tokens: list[str]) -> bool:
    args = tokens[1:]
    index = 0
    while index < len(args):
        token = args[index]
        if token in _GIT_GLOBAL_INSPECT:
            index += 1
            continue
        if token.startswith("-"):
            return False
        break
    if index >= len(args):
        return False
    sub = args[index]
    if sub not in _GIT_INSPECT_SUBS:
        return False
    tail = args[index + 1 :]
    if any(_git_repo_or_output_flag(item) for item in tail):
        return False
    if sub == "branch":
        return _git_branch_list_only(tail)
    return True


def _git_branch_list_only(tail: list[str]) -> bool:
    for item in tail:
        if not item.startswith("-"):
            return False
        if item in _GIT_BRANCH_LIST_FLAGS:
            continue
        if any(item.startswith(prefix) for prefix in _GIT_BRANCH_LIST_PREFIXES):
            continue
        return False
    return True


def _find_inspect_ok(tokens: list[str]) -> bool:
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in {"!", "(", ")", ",", "--"}:
            index += 1
            continue
        if token.startswith("-") and len(token) > 1:
            arity = _FIND_INSPECT_ARITY.get(token)
            if arity is None:
                return False
            index += 1 + arity
            if index > len(tokens):
                return False
            continue
        index += 1
    return True


@dataclass
class ConsentRequest:
    id: str
    bot_id: str
    action_class: str
    scope_key: str
    summary: str
    status: str = "pending"
    run_id: str | None = None
    parent_run_id: str | None = None
    message_id: str | None = None
    job_status: str | None = None


@dataclass
class OwnerQuestion:
    bot_id: str
    run_id: str
    thread_id: str
    waiter: threading.Event
    message_id: str | None = None
    answer: str | None = None
    cancelled: bool = False


from artek_buddy.consent_jobs import OwnerJobTransport  # noqa: E402


class ConsentHub(OwnerJobTransport):
    """Ask before changing the owner PC or leaving the Pi box. Reads do not prompt."""

    def __init__(
        self,
        store: Any,
        events: Any | None = None,
        settings: Any | None = None,
        auto: str | None = None,
    ) -> None:
        self.store = store
        self.events = events
        self.settings = settings
        self.auto = auto
        self._lock = threading.Lock()
        self._waiters: dict[str, threading.Event] = {}
        self._decisions: dict[str, str] = {}
        self._files: dict[str, tuple[str, bytes]] = {}
        self._file_waiters: dict[str, threading.Event] = {}
        self._jobs: dict[str, dict[str, Any]] = {}
        self._job_claims: dict[str, str] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._result_waiters: dict[str, threading.Event] = {}
        self._questions: dict[str, OwnerQuestion] = {}

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

    def _parent_run_id(self, run_id: str | None) -> str | None:
        if not run_id:
            return None
        get_run = getattr(self.store, "get_run", None)
        if callable(get_run) and get_run(run_id) is not None:
            return None
        get_sub = getattr(self.store, "get_subagent", None)
        if not callable(get_sub):
            return None
        found = get_sub(run_id)
        return getattr(found, "parent_run_id", None) if found is not None else None

    def has_grant(
        self, bot_id: str, action_class: str, scope_key: str, device_id: str | None
    ) -> bool:
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
            parent_run_id=self._parent_run_id(run_id),
            thread_id=bot.thread_id,
            message_id=message.id,
            action_class=action_class,
            scope_key=key,
            summary=summary,
            workspace_id=bot.workspace_id,
            job_status="queued" if job else None,
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
    ) -> tuple[bool, str | None]:
        if action_class == CLASS_OWNER_READ:
            return True, None
        key = (scope_key or "*").strip() or "*"
        if self.has_grant(bot_id, action_class, key, device_id):
            return True, None
        mode = self._mode()
        if mode == "allow":
            return True, None
        if mode == "deny":
            return False, None
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
            return False, None
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
        return decision in {"once", "always"}, request_id

    def answer(
        self, request_id: str, decision: str, device_id: str | None
    ) -> ConsentRequest | None:
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
            updated = self.store.answer_message_ask(
                row.message_id,
                LABELS.get(picked, picked),
                include_consent=True,
            )
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

    def wait_decision(self, request_id: str, timeout: float = WAIT_SECONDS) -> str:
        with self._lock:
            waiter = self._waiters.get(request_id)
        if waiter is not None:
            waiter.wait(timeout)
        return self._decisions.get(request_id, "deny")

    def begin_question(self, bot_id: str, run_id: str, thread_id: str) -> bool:
        if not bot_id or not run_id or not thread_id or self.store.get_bot(bot_id) is None:
            return False
        with self._lock:
            if run_id in self._questions:
                return False
            self._questions[run_id] = OwnerQuestion(
                bot_id=bot_id,
                run_id=run_id,
                thread_id=thread_id,
                waiter=threading.Event(),
            )
        return True

    def activate_question(
        self,
        run_id: str,
        message_id: str,
        question: str,
    ) -> bool:
        with self._lock:
            pending = self._questions.get(run_id)
            if pending is None or pending.cancelled:
                return False
            if pending.message_id not in {None, message_id}:
                return False
            pending.message_id = message_id
            if pending.answer is not None:
                return True
            bot = self.store.get_bot(pending.bot_id)
            if bot is None:
                self._questions.pop(run_id, None)
                return False
            self.store.mark_run_waiting_input(run_id)
            self._publish(
                bot,
                ProductEventType.RUN_WAITING_INPUT,
                {
                    "run_id": run_id,
                    "message_id": message_id,
                    "text": question,
                },
                run_id,
            )
        return True

    def answer_question(
        self,
        bot_id: str,
        run_id: str,
        message_id: str,
        answer: str,
    ) -> Any | None:
        text = (answer or "").strip()
        if not text:
            return None
        with self._lock:
            pending = self._questions.get(run_id)
            if pending is None or pending.cancelled or pending.bot_id != bot_id:
                return None
            if pending.message_id is None:
                message = self.store.get_message_in_thread(pending.thread_id, message_id)
                if message is None or message.run_id != run_id:
                    return None
                pending.message_id = message_id
            if pending.message_id != message_id or pending.answer is not None:
                return None
            updated = self.store.answer_message_ask(message_id, text)
            if updated is None:
                return None
            pending.answer = text
            self.store.mark_run_running(run_id)
            bot = self.store.get_bot(bot_id)
            if bot is not None:
                self._publish(
                    bot,
                    ProductEventType.THREAD_MESSAGE_CREATED,
                    {"message": updated.model_dump(mode="json")},
                    run_id,
                )
            pending.waiter.set()
            return updated

    def wait_question(
        self,
        run_id: str,
        timeout: float = OWNER_QUESTION_WAIT,
    ) -> tuple[str | None, str | None]:
        with self._lock:
            pending = self._questions.get(run_id)
        if pending is None:
            return None, "The owner question is no longer active."
        pending.waiter.wait(timeout)
        with self._lock:
            current = self._questions.pop(run_id, None)
            if current is None:
                return None, "The owner question is no longer active."
            answer = current.answer
            cancelled = current.cancelled
        if answer is not None:
            return answer, None
        if cancelled:
            return None, "The owner question was cancelled."
        bot = self.store.get_bot(current.bot_id)
        updated = (
            self.store.answer_message_ask(current.message_id, "Timed out")
            if current.message_id
            else None
        )
        self.store.mark_run_running(run_id)
        if bot is not None and updated is not None:
            self._publish(
                bot,
                ProductEventType.THREAD_MESSAGE_CREATED,
                {"message": updated.model_dump(mode="json")},
                run_id,
            )
        return None, "The owner did not answer in time."

    def abort_question(self, run_id: str) -> None:
        with self._lock:
            pending = self._questions.pop(run_id, None)
        if pending is not None:
            pending.waiter.set()

    def cancel_questions(self, run_ids: list[str]) -> None:
        with self._lock:
            for run_id in run_ids:
                pending = self._questions.get(run_id)
                if pending is None:
                    continue
                pending.cancelled = True
                pending.waiter.set()

    def _publish(
        self, bot: Any, event_type: ProductEventType, payload: dict[str, Any], run_id: str | None
    ) -> None:
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
