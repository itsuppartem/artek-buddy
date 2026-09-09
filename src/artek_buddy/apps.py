from __future__ import annotations

from typing import Any

MAX_APP_ROWS = 20


def format_apps_context(store: Any) -> str:
    lines = [
        "<host_apps>",
        "Connected apps already have tools this turn. Call those tools yourself "
        "when the task needs them; do not wait for a chip or a please-use line. "
        "Search with list_apps(q). Attach with connect_app(slug). If a card has a "
        "login URL, the owner opens it (not the bot desktop), then Finish in Plugins "
        "if needed. Do not create git, SSH, or tokens on this computer for a catalog app.",
    ]
    getter = getattr(store, "raw_connection_key", None) if store is not None else None
    if getter is None or not getter():
        lines.append("No Plugins key. The owner pastes it in Plugins.")
        lines.append("</host_apps>")
        return "\n".join(lines)
    listed = store.list_connections()
    names = [
        str(row.display_name)
        for row in listed.connections
        if getattr(row, "status", "") == "connected"
    ]
    lines.append("Connected: " + (", ".join(names) if names else "none"))
    lines.append("</host_apps>")
    return "\n".join(lines)
