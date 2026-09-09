from __future__ import annotations

STATUS_PING_GUIDE = (
    "On a status-only ping (progress, 'как там?', 'ну что там?', 'ты завис?', "
    "'еще делаешь?'): call send_message first with a short truthful acknowledgement. "
    "Then inspect_subagent or list_subagents if you need host activity. "
    "Do not start a new plan, infer a new task, spawn a replacement, "
    "or call stop_subagent / restart_subagent. "
    "Empty progress is no text update, not idle."
)
