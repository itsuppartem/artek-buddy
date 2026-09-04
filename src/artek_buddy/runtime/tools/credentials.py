from __future__ import annotations

from dataclasses import asdict
from typing import Any

from artek_buddy.bot_credentials import CredentialStoreError


class CredentialsToolsMixin:
    def _exec_list_bot_credentials(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
        bot_id, _run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if not bot_id:
            return {"ok": False, "error": "no active bot"}
        store = getattr(self.runtime, "credential_store", None)
        if store is None:
            return {"ok": False, "error": "credential broker unavailable"}
        try:
            rows = store.list_for_bot(bot_id)
        except CredentialStoreError:
            return {"ok": False, "error": "credential broker unavailable"}
        return {
            "ok": True,
            "scope": "this_bot",
            "credentials": [
                {
                    "provider": row.provider,
                    "last_four": row.last_four,
                    "present": True,
                }
                for row in rows
            ],
        }

    def _exec_run_credential_scoped_command(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
        bot_id, _run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if not bot_id:
            return {"ok": False, "error": "no active bot"}
        command = str(args.get("command") or "").strip()
        if not command:
            return {"ok": False, "error": "command is required"}
        store = getattr(self.runtime, "store", None)
        credentials = getattr(self.runtime, "credential_store", None)
        if store is None or credentials is None:
            return {"ok": False, "error": "credential broker unavailable"}
        bot = store.get_bot(bot_id)
        if bot is None:
            return {"ok": False, "error": "bot not found"}
        record = store.get_computer_for_bot(bot)
        try:
            timeout = float(args.get("timeout_seconds") or 30)
            result = credentials.execute(
                bot_id,
                record.home_key,
                command,
                cwd=str(args.get("cwd") or "."),
                timeout_seconds=timeout,
            )
        except (CredentialStoreError, OSError):
            return {"ok": False, "error": "credential broker unavailable"}
        except (TypeError, ValueError) as err:
            return {"ok": False, "error": str(err)}
        return asdict(result)
