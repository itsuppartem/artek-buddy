from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncIterator

from artek_buddy.contracts.events import ProductEvent

HEARTBEAT = object()


class EventHub:
    """In-process fan-out for thread SSE. Not durable across process restart."""

    def __init__(self, buffer_size: int = 200) -> None:
        self.buffer_size = buffer_size
        self._subs: dict[str, set[asyncio.Queue[ProductEvent]]] = defaultdict(set)
        self._buf: dict[str, list[ProductEvent]] = defaultdict(list)
        self._seq: dict[str, int] = defaultdict(int)

    def next_seq(self, bot_id: str) -> int:
        self._seq[bot_id] += 1
        return self._seq[bot_id]

    def publish(self, event: ProductEvent) -> None:
        bot_id = event.bot_id
        buf = self._buf[bot_id]
        buf.append(event)
        if len(buf) > self.buffer_size:
            del buf[: len(buf) - self.buffer_size]
        for queue in list(self._subs[bot_id]):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    def replay(self, bot_id: str, after: str | None = None) -> list[ProductEvent]:
        items = list(self._buf.get(bot_id, ()))
        if not after:
            return items
        seen = False
        out: list[ProductEvent] = []
        for event in items:
            if seen:
                out.append(event)
            elif event.id == after:
                seen = True
        return out

    async def subscribe(
        self,
        bot_id: str,
        after: str | None = None,
        heartbeat_s: float = 15.0,
    ) -> AsyncIterator[ProductEvent | object]:
        queue: asyncio.Queue[ProductEvent] = asyncio.Queue(maxsize=256)
        self._subs[bot_id].add(queue)
        try:
            for event in self.replay(bot_id, after=after):
                yield event
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
                    yield event
                except asyncio.TimeoutError:
                    yield HEARTBEAT
        finally:
            self._subs[bot_id].discard(queue)
