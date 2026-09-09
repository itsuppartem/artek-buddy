from __future__ import annotations

from types import SimpleNamespace

from artek_buddy.http import bot_ask_delivery, turn_registry, turns


class _FakeTask:
    def __init__(self) -> None:
        self.cancelled = False
        self._done = False

    def done(self) -> bool:
        return self._done

    def cancel(self) -> None:
        self.cancelled = True
        self._done = True


def _app(monkeypatch) -> SimpleNamespace:
    app = SimpleNamespace(state=SimpleNamespace(active_turns={}))
    monkeypatch.setattr(turn_registry, "current_app", lambda: app)
    return app


def test_register_then_drop_clears_an_empty_bot_bucket(monkeypatch) -> None:
    app = _app(monkeypatch)
    task = _FakeTask()
    turn_registry.register_turn("bot-a", "run-1", task)
    assert app.state.active_turns["bot-a"]["run-1"] is task
    turn_registry.drop_turn("bot-a", "run-1")
    assert app.state.active_turns == {}


def test_cancel_one_run_leaves_the_other(monkeypatch) -> None:
    app = _app(monkeypatch)
    keep = _FakeTask()
    stop = _FakeTask()
    turn_registry.register_turn("bot-a", "keep", keep)
    turn_registry.register_turn("bot-a", "stop", stop)
    turn_registry.cancel_turns("bot-a", "stop")
    assert stop.cancelled is True
    assert keep.cancelled is False
    assert "keep" in app.state.active_turns["bot-a"]


def test_cancel_bot_without_run_id_drops_the_bucket(monkeypatch) -> None:
    _app(monkeypatch)
    first = _FakeTask()
    second = _FakeTask()
    turn_registry.register_turn("bot-a", "a", first)
    turn_registry.register_turn("bot-a", "b", second)
    turn_registry.cancel_turns("bot-a")
    assert first.cancelled is True
    assert second.cancelled is True
    assert turn_registry.current_app().state.active_turns == {}


def test_turns_uses_registry_and_bot_ask_delivery() -> None:
    assert turns._register_turn is turn_registry.register_turn
    assert turns._drop_turn is turn_registry.drop_turn
    assert turns._cancel_turns is turn_registry.cancel_turns
    assert turns._deliver_bot_ask_reply is bot_ask_delivery.deliver_bot_ask_reply
