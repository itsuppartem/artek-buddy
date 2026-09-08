from __future__ import annotations

import logging
from typing import Any

from artek_buddy.bus import EventHub
from artek_buddy.contracts import Bot, ProductEvent, ProductEventType
from artek_buddy.db.history import HistoryStore
from artek_buddy.db.shaping import isoformat_utc, new_id
from artek_buddy.runtime.token_usage import TokenUsage

log = logging.getLogger("artek_buddy")


def persist_product_usage(
    history: HistoryStore,
    events: EventHub | None,
    bot: Bot,
    run_id: str,
    usage: TokenUsage | None,
) -> None:
    """Store counts for a product run. Missing usage is a no-op, never a failed turn."""
    if usage is None:
        return
    try:
        record = history.record_usage(
            bot_id=bot.id,
            run_id=run_id,
            provider=usage.provider,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            total_tokens=usage.total_tokens,
        )
    except Exception:
        log.exception("failed to persist usage for run %s", run_id)
        return
    if record is None or events is None:
        return
    try:
        payload: dict[str, Any] = {
            "run_id": run_id,
            "bot_id": bot.id,
            **usage.counts_payload(),
        }
        event = ProductEvent(
            id=new_id("evt"),
            workspace_id=bot.workspace_id,
            thread_id=bot.thread_id,
            bot_id=bot.id,
            seq=events.next_seq(bot.id),
            type=ProductEventType.USAGE_RECORDED,
            created_at=isoformat_utc(),
            payload=payload,
            run_id=run_id,
        )
        events.publish(event)
    except Exception:
        log.exception("failed to emit usage.recorded for run %s", run_id)
