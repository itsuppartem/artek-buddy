from __future__ import annotations

import asyncio

from artek_buddy.bus import HEARTBEAT, EventHub
from artek_buddy.contracts.events import ProductEvent, ProductEventType


def _event(bot_id: str, event_id: str) -> ProductEvent:
    return ProductEvent(
        id=event_id,
        workspace_id="ws",
        thread_id=f"thr_{bot_id}",
        bot_id=bot_id,
        seq=1,
        type=ProductEventType.THREAD_MESSAGE_CREATED,
        created_at="2026-08-20T00:00:00Z",
        payload={},
    )


def test_event_hub_buffers_and_sequences() -> None:
    hub = EventHub(buffer_size=3)
    bot = "bot_1"
    for index in range(4):
        hub.publish(
            ProductEvent(
                id=f"ev_{index}",
                workspace_id="ws",
                thread_id="thr",
                bot_id=bot,
                seq=hub.next_seq(bot),
                type=ProductEventType.THREAD_MESSAGE_UPDATED,
                created_at="2026-08-19T00:00:00Z",
                payload={"n": index},
            )
        )
    assert hub.next_seq(bot) == 5
    assert len(hub._buf[bot]) == 3


def test_workspace_subscribe_receives_every_bot() -> None:
    """One inbox stream must fan out every bot so the window does not open N SSE sockets."""
    asyncio.run(_assert_workspace_fanout())


async def _assert_workspace_fanout() -> None:
    hub = EventHub()
    received: list[str] = []

    async def collect() -> None:
        async for item in hub.subscribe_workspace(heartbeat_s=0.2):
            if item is HEARTBEAT:
                continue
            received.append(item.bot_id)
            if len(received) >= 2:
                return

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.02)
    hub.publish(_event("bot_a", "evt_a"))
    hub.publish(_event("bot_b", "evt_b"))
    await asyncio.wait_for(task, timeout=1)
    assert received == ["bot_a", "bot_b"]


def test_publish_from_worker_thread_wakes_subscriber() -> None:
    """Auto owner jobs publish from a worker thread. asyncio.Queue must still wake SSE."""
    asyncio.run(_assert_thread_publish())


async def _assert_thread_publish() -> None:
    import threading

    hub = EventHub()
    received: list[str] = []

    async def collect() -> None:
        async for item in hub.subscribe("bot_a", heartbeat_s=2.0):
            if item is HEARTBEAT:
                continue
            received.append(item.id)
            return

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.05)

    def worker() -> None:
        hub.publish(_event("bot_a", "from_thread"))

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    await asyncio.wait_for(task, timeout=1)
    assert received == ["from_thread"]
