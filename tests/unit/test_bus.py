from __future__ import annotations

from artek_buddy.bus import EventHub
from artek_buddy.contracts.events import ProductEvent, ProductEventType


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
