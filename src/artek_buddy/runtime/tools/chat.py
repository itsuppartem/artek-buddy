from __future__ import annotations

import base64
import logging
import mimetypes
import shutil
from typing import Any

from pathlib import Path

from artek_buddy.consent import (
    CLASS_BROWSE,
    CLASS_OWNER_EXEC,
    CLASS_OWNER_READ,
    CLASS_OWNER_WRITE,
    CLASS_PAGE,
    OWNER_HOME_SCOPE,
    browse_origin,
    owner_command_is_readonly,
)
from artek_buddy.contracts.events import ProductEvent, ProductEventType
from artek_buddy.db.shaping import isoformat_utc, new_id
from artek_buddy.runtime.tools.common import (
    CONSENT_DONE,
    MAX_INLINE_FILE_BYTES,
    MAX_SEND_FILE_BYTES,
    PAGE_KINDS,
    _is_under,
    _playwright_browser_command,
    _safe_filename,
    _with_consent,
    emit_computer_event,
    format_owner_steer,
    log,
)
from artek_buddy.runtime.tools.specs import TOOL_SPECS, ToolSpec


class ChatToolsMixin:
    def _exec_remember(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        content = str(args.get("content") or "").strip()
        path = str(args.get("path") or "").strip()
        if not content:
            return {"ok": False, "error": "content cannot be empty"}
        bot_id, run_id, thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        forget = bool(args.get("forget"))
        kind = str(args.get("kind") or "preference")
        if args.get("scope"):
            scope = str(args.get("scope"))
        elif getattr(self.runtime, "resolve_turn_role", lambda: "lead")() == "subagent":
            scope = "bot"
        else:
            scope = "user"
        hub = getattr(self.runtime, "memory", None)
        if hub is not None:
            try:
                if forget:
                    removed = hub.forget(content, bot_id=bot_id)
                    return {"ok": True, "forgotten": removed}
                entry = hub.capture(
                    content,
                    kind=kind,
                    scope=scope,
                    bot_id=bot_id,
                    source="remember",
                    run_id=run_id,
                    thread_id=thread_id,
                    slot=str(args.get("slot") or "") or None,
                )
                if entry is None:
                    return {"ok": True, "saved": False}
                return {
                    "ok": True,
                    "entry_id": entry.id,
                    "document_id": entry.document_id,
                    "scope": entry.scope,
                    "kind": entry.kind,
                }
            except Exception as exc:
                log.exception("failed to save memory in remember tool")
                return {"ok": False, "error": str(exc)}
        if self.runtime.store is not None:
            try:
                if not path or path == "MEMORY.md":
                    from artek_buddy.db.shaping import new_id
                    from artek_buddy.memory_hub import entry_path, normalize_kind

                    path = entry_path(
                        new_id("ment"),
                        normalize_kind(kind),
                        "charter" if scope == "bot" else "owner",
                    )
                doc = self.runtime.store.save_memory(
                    scope="bot" if scope == "bot" and bot_id else "user",
                    path=path,
                    content=content,
                    bot_id=bot_id,
                    source_run_id=run_id,
                    source_thread_id=thread_id,
                )
                return {
                    "ok": True,
                    "document_id": doc.id,
                    "revision": doc.revision,
                    "path": doc.path,
                    "scope": doc.scope.value if hasattr(doc.scope, "value") else str(doc.scope),
                }
            except Exception as exc:
                log.exception("failed to save memory in remember tool")
                return {"ok": False, "error": str(exc)}
        return {"ok": True, "saved": False}

    def _append_bot_blocks(
        self,
        args: dict[str, Any],
        bound_bot_id: str | None,
        blocks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        bot_id, run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if self.runtime.store is None or not bot_id:
            return {"ok": False, "error": "store is not available"}
        bot = self.runtime.store.get_bot(bot_id)
        if bot is None:
            return {"ok": False, "error": "bot not found"}
        try:
            msg = self.runtime.store.append_bot_message(bot, blocks, run_id=run_id)
            self.runtime.mark_message_sent(run_id)
            if self.runtime.events is not None:
                event = ProductEvent(
                    id=new_id("evt"),
                    workspace_id=bot.workspace_id,
                    thread_id=bot.thread_id,
                    bot_id=bot.id,
                    seq=self.runtime.events.next_seq(bot.id),
                    type=ProductEventType.THREAD_MESSAGE_CREATED,
                    created_at=isoformat_utc(),
                    payload={"message": msg.model_dump(mode="json")},
                    run_id=run_id,
                )
                self.runtime.events.publish(event)
            return {"ok": True, "message_id": msg.id}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _exec_send_message(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        text = str(args.get("text") or args.get("message") or "").strip()
        if not text:
            return {"ok": False, "error": "text is required"}
        raw_options = args.get("options")
        if isinstance(raw_options, list) and raw_options:
            actions = [{"id": f"opt_{i+1}", "label": str(opt)} for i, opt in enumerate(raw_options)]
            blocks = [
                {
                    "kind": "ask",
                    "text": text,
                    "detail": str(args.get("detail") or "").strip() or None,
                    "status": "pending",
                    "actions": actions,
                }
            ]
        else:
            blocks = [{"kind": "text", "text": text}]
        return self._append_bot_blocks(args, bound_bot_id, blocks)

    def _agent_file_roots(self, bot_id: str | None) -> list[Path]:
        roots: list[Path] = []
        home = Path(self.runtime.home_cwd(bot_id))
        roots.append(home)
        workspace = Path(getattr(self.runtime.settings, "agent_cwd", "") or home)
        if workspace.resolve() != home.resolve():
            roots.append(workspace)
        return roots

    def _resolve_agent_file(self, bot_id: str | None, raw: str) -> Path | None:
        text = str(raw or "").strip()
        if not text:
            return None
        path = Path(text)
        roots = self._agent_file_roots(bot_id)
        candidates: list[Path] = []
        if path.is_absolute():
            candidates.append(path)
        else:
            candidates.extend(root / path for root in roots)
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved.is_file() and any(_is_under(resolved, root) for root in roots):
                return resolved
        return None

    def _exec_send_file(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        bot_id, run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        path_raw = str(args.get("path") or "").strip()
        display = _safe_filename(str(args.get("name") or path_raw or "file"))
        caption = str(args.get("text") or "").strip()
        content = args.get("content")
        source: Path | None = None
        if content is not None:
            if not isinstance(content, str):
                return {"ok": False, "error": "content must be text"}
            data = content.encode("utf-8")
            if len(data) > MAX_INLINE_FILE_BYTES:
                return {"ok": False, "error": "content is too large"}
            if not path_raw:
                path_raw = display
            home = Path(self.runtime.home_cwd(bot_id))
            home.mkdir(parents=True, exist_ok=True)
            source = home / _safe_filename(path_raw)
            source.write_bytes(data)
        else:
            source = self._resolve_agent_file(bot_id, path_raw)
        if source is None or not source.is_file():
            return {"ok": False, "error": "file not found"}
        size = source.stat().st_size
        if size > MAX_SEND_FILE_BYTES:
            return {"ok": False, "error": "file too large"}
        name = _safe_filename(str(args.get("name") or source.name or display))
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        store = getattr(self.runtime, "store", None)
        if store is None or not hasattr(store, "save_artifact"):
            return {"ok": False, "error": "artifacts unavailable"}
        bot = store.get_bot(bot_id) if bot_id else None
        if bot is None:
            return {"ok": False, "error": "bot not found"}
        artifact_id = new_id("art")
        dest_dir = Path(self.runtime.settings.agent_data_dir) / "artifacts" / bot.id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / artifact_id
        shutil.copy2(source, dest)
        try:
            store.save_artifact(
                bot_id=bot.id,
                name=name,
                mime_type=mime,
                size=size,
                storage_path=str(dest),
                run_id=run_id,
                artifact_id=artifact_id,
            )
        except Exception as exc:
            dest.unlink(missing_ok=True)
            return {"ok": False, "error": str(exc)}
        blocks: list[dict[str, Any]] = []
        if caption:
            blocks.append({"kind": "text", "text": caption})
        blocks.append(
            {
                "kind": "file",
                "artifact_id": artifact_id,
                "name": name,
                "mime_type": mime,
                "size": size,
            }
        )
        posted = self._append_bot_blocks(args, bound_bot_id, blocks)
        if not posted.get("ok"):
            return posted
        posted["artifact_id"] = artifact_id
        posted["name"] = name
        posted["size"] = size
        return posted

    def _exec_ask_user(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        question = str(args.get("question") or args.get("text") or "").strip()
        if not question:
            return {"ok": False, "error": "question is required"}
        raw_options = args.get("options") or []
        if not isinstance(raw_options, list) or not raw_options:
            return {"ok": False, "error": "options list is required"}
        actions = [{"id": f"opt_{i+1}", "label": str(opt)} for i, opt in enumerate(raw_options)]
        detail = str(args.get("detail") or "").strip() or None
        blocks = [
            {
                "kind": "ask",
                "text": question,
                "detail": detail,
                "status": "pending",
                "actions": actions,
            }
        ]
        return self._append_bot_blocks(args, bound_bot_id, blocks)

