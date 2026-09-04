from __future__ import annotations

from types import SimpleNamespace

from artek_buddy.runtime.tools.product import ProductToolsCore
from artek_buddy.workspace_dispatch import format_workspace_context, parse_dispatch_target


def _bot(bot_id: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=bot_id,
        name=name,
        title=f"{name} title",
        description=f"{name} description",
        status="idle",
        preview=f"{name} last result",
        thread_id=f"thread-{bot_id}",
    )


def test_parse_dispatch_target_accepts_only_a_known_bot_id() -> None:
    bots = [_bot("bot_mail", "Mail"), _bot("bot_code", "Code")]

    assert parse_dispatch_target('{"bot_id":"bot_code"}', bots).id == "bot_code"


def test_workspace_context_contains_profiles_and_recent_thread_context() -> None:
    bots = [_bot("bot_mail", "Mail")]

    text = format_workspace_context(
        bots,
        {"bot_mail": "user: Draft a reply\nbot: Draft is ready"},
    )

    assert '"id": "bot_mail"' in text
    assert "Mail description" in text
    assert "Draft is ready" in text


def test_workspace_dispatcher_cannot_run_product_tools() -> None:
    runtime = SimpleNamespace(store=None, settings=None)

    assert ProductToolsCore(runtime).specs("dispatcher") == []
