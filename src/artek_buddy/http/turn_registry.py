"""In-flight turn tasks keyed by bot, separate from bot-ask delivery."""

from __future__ import annotations

import asyncio
from typing import Any

from artek_buddy.http.deps import current_app


def turn_bucket(bot_id: str) -> dict[str, asyncio.Task[Any]]:
    turns = getattr(current_app().state, "active_turns", None)
    if turns is None:
        return {}
    bucket = turns.get(bot_id)
    if bucket is None:
        bucket = {}
        turns[bot_id] = bucket
    return bucket


def register_turn(bot_id: str, run_id: str, task: asyncio.Task[Any]) -> None:
    turn_bucket(bot_id)[run_id] = task


def drop_turn(bot_id: str, run_id: str) -> None:
    turns = getattr(current_app().state, "active_turns", None)
    if not turns:
        return
    bucket = turns.get(bot_id)
    if not bucket:
        return
    bucket.pop(run_id, None)
    if not bucket:
        turns.pop(bot_id, None)


def cancel_turns(bot_id: str, run_id: str | None = None) -> None:
    turns = getattr(current_app().state, "active_turns", None)
    if not turns:
        return
    bucket = turns.get(bot_id) or {}
    if run_id:
        tasks = [bucket[run_id]] if run_id in bucket else []
    else:
        tasks = list(bucket.values())
        turns.pop(bot_id, None)
    for task in tasks:
        if task and not task.done():
            task.cancel()
