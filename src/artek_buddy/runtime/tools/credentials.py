from __future__ import annotations

from typing import Any

from artek_buddy.bot_credentials import BotCredentialStore


class CredentialsToolsMixin:
    def _exec_list_bot_credentials(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
        bot_id, _run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if not bot_id:
            return {"ok": False, "error": "no active bot"}
        data_dir = getattr(self.runtime.settings, "agent_data_dir", "/data")
        rows = BotCredentialStore(data_dir).list_for_bot(bot_id)
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
