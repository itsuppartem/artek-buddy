from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import artek_buddy.consent as consent_mod
from artek_buddy.consent import (
    ConsentHub,
    ConsentRequest,
    browse_origin,
    decision_from_label,
    owner_command_is_readonly,
    owner_scope,
)


def test_decision_from_label_happy_and_fail() -> None:
    assert decision_from_label("Allow once") == "once"
    assert decision_from_label("Always") == "always"
    assert decision_from_label("Deny") == "deny"
    assert decision_from_label("maybe later") is None


def test_browse_origin_requires_http_host() -> None:
    assert browse_origin("https://example.com/path") == "https://example.com"
    assert browse_origin("www.example.com") == "https://www.example.com"
    assert browse_origin("not a url") is None
    assert browse_origin("") is None


def test_owner_scope_uses_parent() -> None:
    assert owner_scope("~/notes.txt") == "~"
    assert owner_scope("/home/artek/a/b") == "/home/artek/a"


def test_owner_readonly_commands() -> None:
    assert owner_command_is_readonly("ls -la ~") is True
    assert owner_command_is_readonly("cat notes.txt") is True
    assert owner_command_is_readonly("rm -rf ~") is False
    assert owner_command_is_readonly("echo hi > file") is False
    assert owner_command_is_readonly("git status") is True
    assert owner_command_is_readonly("git commit -am x") is False


class _ConsentStore:
    def get_bot(self, _bot_id: str) -> None:
        return None

    def get_consent_request(self, request_id: str) -> ConsentRequest:
        return ConsentRequest(
            id=request_id,
            bot_id="bot_1",
            action_class="owner_read",
            scope_key="~",
            summary="Read notes.txt from your computer?",
        )


def test_take_owner_file_unblocks_when_client_reports_error(monkeypatch) -> None:
    """A failed auto fulfill posts a result, not a file. Do not sit on the file waiter."""
    monkeypatch.setattr(consent_mod, "OWNER_FILE_WAIT", 5)
    hub = ConsentHub(_ConsentStore())
    started = threading.Event()
    found: list[object] = []

    def wait() -> None:
        started.set()
        found.append(hub.take_owner_file("cns_1"))

    worker = threading.Thread(target=wait)
    worker.start()
    assert started.wait(1)
    time.sleep(0.05)
    assert hub.put_owner_result("cns_1", {"ok": False, "error": "could not read file"})
    t0 = time.monotonic()
    worker.join(timeout=1.5)
    assert worker.is_alive() is False
    assert time.monotonic() - t0 < 1.2
    assert found == [None]


def test_auto_owner_read_publishes_consent_on_waiting_input() -> None:
    published: list[object] = []

    class Events:
        def next_seq(self, _bot_id: str) -> int:
            return len(published) + 1

        def publish(self, event: object) -> None:
            published.append(event)

    class Store:
        def get_bot(self, bot_id: str) -> object:
            return SimpleNamespace(id=bot_id, workspace_id="ws", thread_id="thr_1")

        def create_consent_request(self, *_args: object, **_kwargs: object) -> None:
            return None

        def mark_run_waiting_input(self, _run_id: str) -> None:
            return None

    hub = ConsentHub(Store(), events=Events())
    request_id = hub.start_auto_owner_read(
        bot_id="bot_1",
        path="notes.txt",
        run_id="run_1",
        device_id=None,
    )
    assert request_id
    event = published[-1]
    assert event.type.value == "run.waiting_input"
    assert event.payload["auto"] is True
    assert event.payload["consent_id"] == request_id
    assert event.payload["action_class"] == "owner_read"
    assert event.payload["path"] == "notes.txt"
