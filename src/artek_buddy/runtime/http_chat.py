from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from artek_buddy.db.shaping import new_id
from artek_buddy.model_catalog import complete_chat
from artek_buddy.runtime.base import RuntimeBase
from artek_buddy.runtime.types import ProductStreamEvent, RunRecord

log = logging.getLogger("artek_buddy")


class HttpChatRuntime(RuntimeBase):
    async def start(self) -> None:
        self._ensure_dirs()
        live = await self.ensure_session(None, name="artek-buddy")
        self.default_agent_id = live
        self._save_state(live)
        log.info("http chat runtime ready default_agent=%s", live)

    async def create_session(
        self,
        name: str = "artek-buddy",
        persist_default: bool = False,
        bot_id: str | None = None,
        role: str = "lead",
    ) -> str:
        agent_id = new_id("ag")
        self._agents[agent_id] = {"name": name, "role": role}
        self.bind_agent_bot(agent_id, bot_id)
        if persist_default or self.default_agent_id is None:
            self.default_agent_id = agent_id
            self._save_state(agent_id)
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
        if self.default_agent_id:
            return await self.create_session(
                name=name,
                persist_default=False,
                bot_id=bot_id,
                role=role,
            )
        return await self.create_session(
            name=name,
            persist_default=self.default_agent_id is None,
            bot_id=bot_id,
            role=role,
        )

    async def list_models(self) -> list[dict[str, str]]:
        if self.store is None:
            return []
        return self.store.list_catalog()

    async def stream(
        self,
        prompt: str,
        session_id: str | None = None,
        bot_id: str | None = None,
        role: str = "lead",
    ) -> AsyncIterator[ProductStreamEvent | RunRecord]:
        agent_id = await self.ensure_session(session_id, bot_id=bot_id, role=role)
        default = self.store.get_default_model() if self.store is not None else None
        text = ""
        if default is not None:
            provider, model = default
            key = self.store.raw_key(provider) if self.store is not None else None
            if key:
                text = await complete_chat(provider, key, model, prompt)
        yield ProductStreamEvent(
            "thread.message.updated",
            {"text": text, "kind": "text", "replace": True},
        )
        yield RunRecord(id=new_id("run"), agent_id=agent_id, status="completed", result=text)
