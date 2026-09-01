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
from artek_buddy.runtime.tools.product import ProductToolsCore


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
            job_status="queued",
            run_id="run_1",
        )

    def owner_job_ids_for_runs(self, run_ids: list[str]) -> list[str]:
        if "run_1" in run_ids:
            return ["cns_1"]
        return []

    def finish_consent_job(self, _request_id: str, _job_status: str) -> bool:
        return True


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
    assert not hasattr(hub, "last_request_id")


def test_owner_question_timeout_is_explicit_and_resumes_the_run() -> None:
    published: list[object] = []

    class Events:
        def next_seq(self, _bot_id: str) -> int:
            return len(published) + 1

        def publish(self, event: object) -> None:
            published.append(event)

    class Store:
        def __init__(self) -> None:
            self.statuses: list[str] = []
            self.answer: str | None = None

        def get_bot(self, bot_id: str) -> object:
            return SimpleNamespace(id=bot_id, workspace_id="ws", thread_id="thr_1")

        def mark_run_waiting_input(self, _run_id: str) -> None:
            self.statuses.append("waiting_input")

        def mark_run_running(self, _run_id: str) -> None:
            self.statuses.append("running")

        def answer_message_ask(
            self, _message_id: str, answer: str, *, include_consent: bool = False
        ) -> object:
            assert include_consent is False
            self.answer = answer
            return SimpleNamespace(model_dump=lambda **_kwargs: {"id": "msg_1"})

    store = Store()
    hub = ConsentHub(store, events=Events())
    assert hub.begin_question("bot_1", "run_1", "thr_1") is True
    assert hub.activate_question("run_1", "msg_1", "Please finish the browser step") is True

    answer, error = hub.wait_question("run_1", timeout=0)

    assert answer is None
    assert error == "The owner did not answer in time."
    assert store.answer == "Timed out"
    assert store.statuses == ["waiting_input", "running"]
    assert [event.type.value for event in published] == [
        "run.waiting_input",
        "thread.message.created",
    ]


def test_owner_result_wait_uses_the_current_call_request_id() -> None:
    class Hub:
        def _mode(self) -> None:
            return None

        def take_owner_result(self, request_id: str, **_kwargs: object) -> dict[str, object]:
            return {"ok": True, "request_id": request_id}

    runtime = SimpleNamespace(
        consent=Hub(),
        resolve_turn_device=lambda: "dev_1",
    )
    tools = ProductToolsCore(runtime)

    second = tools._owner_client_result(
        bot_id="bot_2",
        run_id="run_2",
        action_class="owner_exec",
        scope_key="~",
        summary="Run second?",
        job={"kind": "exec", "command": "echo second"},
        request_id="cns_second",
    )

    assert second == {"ok": True, "request_id": "cns_second"}


def test_ack_claims_owner_job_once_and_late_result_is_rejected() -> None:
    class Store:
        def __init__(self) -> None:
            self.row = ConsentRequest(
                id="cns_1",
                bot_id="bot_1",
                action_class="owner_exec",
                scope_key="~",
                summary="Run it?",
                job_status="queued",
            )

        def get_consent_request(self, _request_id: str) -> ConsentRequest:
            return self.row

        def acknowledge_consent_job(self, _request_id: str) -> bool:
            if self.row.job_status != "queued":
                return False
            self.row.job_status = "acknowledged"
            return True

        def finish_consent_job(self, _request_id: str, job_status: str) -> bool:
            if self.row.job_status not in {"queued", "acknowledged"}:
                return False
            self.row.job_status = job_status
            return True

    store = Store()
    hub = ConsentHub(store)

    assert hub.acknowledge_owner_job("cns_1") is True
    assert hub.acknowledge_owner_job("cns_1") is False
    assert hub.put_owner_result("cns_1", {"ok": True, "stdout": "done"}) is True
    assert store.row.job_status == "completed"
    assert hub.put_owner_result("cns_1", {"ok": True, "stdout": "late"}) is False


def test_claim_capable_ack_rejects_a_result_without_the_claim() -> None:
    class Store:
        def __init__(self) -> None:
            self.row = ConsentRequest(
                id="cns_1",
                bot_id="bot_1",
                action_class="owner_exec",
                scope_key="~",
                summary="Run it?",
                job_status="queued",
            )

        def get_consent_request(self, _request_id: str) -> ConsentRequest:
            return self.row

        def acknowledge_consent_job(self, _request_id: str) -> bool:
            if self.row.job_status != "queued":
                return False
            self.row.job_status = "acknowledged"
            return True

        def finish_consent_job(self, _request_id: str, job_status: str) -> bool:
            if self.row.job_status not in {"queued", "acknowledged"}:
                return False
            self.row.job_status = job_status
            return True

    store = Store()
    hub = ConsentHub(store)

    claimed, claim = hub.claim_owner_job("cns_1", claim_capable=True)
    assert claimed is True
    assert claim
    assert hub.put_owner_result("cns_1", {"ok": False}, claim=None) is False
    assert hub.put_owner_result("cns_1", {"ok": False}, claim="wrong") is False
    assert store.row.job_status == "acknowledged"
    assert hub.put_owner_result("cns_1", {"ok": True}, claim=claim) is True
    assert store.row.job_status == "completed"


def test_cancel_owner_jobs_wakes_result_wait(monkeypatch) -> None:
    monkeypatch.setattr(consent_mod, "OWNER_RESULT_WAIT", 5)
    hub = ConsentHub(_ConsentStore())
    started = threading.Event()
    found: list[object] = []

    def wait() -> None:
        started.set()
        found.append(hub.take_owner_result("cns_1", finalize_timeout=False))

    worker = threading.Thread(target=wait)
    worker.start()
    assert started.wait(1)
    time.sleep(0.05)
    hub.cancel_owner_jobs(["run_1"])
    worker.join(1)
    assert not worker.is_alive()
    assert found
    result = found[0]
    assert isinstance(result, dict)
    assert result.get("ok") is False
    assert result.get("error") == "Stopped."
