from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator

from artek_buddy.contracts.events import ProductEvent

HEARTBEAT = object()
REPLAY_GAP = object()
WORKSPACE_CHANNEL = "*"


class EventHub:
    """In-process fan-out for thread SSE. Not durable across process restart."""

    def __init__(self, buffer_size: int = 200) -> None:
        self.buffer_size = buffer_size
        self._subs: dict[str, set[asyncio.Queue[ProductEvent]]] = defaultdict(set)
        self._buf: dict[str, list[ProductEvent]] = defaultdict(list)
        self._seq: dict[str, int] = defaultdict(int)
        self._loop: asyncio.AbstractEventLoop | None = None

    def next_seq(self, bot_id: str) -> int:
        self._seq[bot_id] += 1
        return self._seq[bot_id]

    def _bind_loop(self) -> None:
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

    def publish(self, event: ProductEvent) -> None:
        bot_id = event.bot_id
        buf = self._buf[bot_id]
        buf.append(event)
        if len(buf) > self.buffer_size:
            del buf[: len(buf) - self.buffer_size]
        self._deliver(event, self._subs[bot_id])
        self._deliver(event, self._subs[WORKSPACE_CHANNEL])

    def _deliver(self, event: ProductEvent, queues: set[asyncio.Queue[ProductEvent]]) -> None:
        for queue in list(queues):
            self._enqueue(queue, event)

    def _enqueue(self, queue: asyncio.Queue[ProductEvent], event: ProductEvent) -> None:
        def put() -> None:
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

        loop = self._loop
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if loop is not None and loop.is_running() and running is not loop:
            loop.call_soon_threadsafe(put)
        else:
            put()

    def has_event(self, bot_id: str, event_id: str) -> bool:
        return any(event.id == event_id for event in self._buf.get(bot_id, ()))

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
        self._bind_loop()
        self._subs[bot_id].add(queue)
        try:
            yield HEARTBEAT
            if after and not self.has_event(bot_id, after):
                yield REPLAY_GAP
            else:
                for event in self.replay(bot_id, after=after):
                    yield event
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
                    yield event
                except TimeoutError:
                    yield HEARTBEAT
        finally:
            self._subs[bot_id].discard(queue)

    async def subscribe_workspace(
        self,
        heartbeat_s: float = 15.0,
    ) -> AsyncIterator[ProductEvent | object]:
        queue: asyncio.Queue[ProductEvent] = asyncio.Queue(maxsize=256)
        self._bind_loop()
        self._subs[WORKSPACE_CHANNEL].add(queue)
        try:
            yield HEARTBEAT
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
                    yield event
                except TimeoutError:
                    yield HEARTBEAT
        finally:
            self._subs[WORKSPACE_CHANNEL].discard(queue)
