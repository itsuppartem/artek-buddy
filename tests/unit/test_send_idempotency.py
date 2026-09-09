from __future__ import annotations

import json
from urllib.request import Request

from artek_buddy.contracts.domain import ThreadSendInput
from artek_buddy.worker import wake_routine


def test_thread_send_input_accepts_job_idempotency_key() -> None:
    body = ThreadSendInput(text="hello", trigger="routine", idempotency_key="job_ab12cd34")
    assert body.idempotency_key == "job_ab12cd34"
    owner = ThreadSendInput(text="hello")
    assert owner.trigger == "user"
    assert owner.idempotency_key is None


def test_routine_wake_posts_job_id_as_idempotency_key(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Resp:
        status = 200

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    def fake_urlopen(req: Request, timeout: float | None = None) -> _Resp:
        del timeout
        captured["body"] = json.loads(req.data.decode())
        return _Resp()

    monkeypatch.setattr("artek_buddy.worker.urllib.request.urlopen", fake_urlopen)
    assert wake_routine("http://127.0.0.1:9", "tok", "bot_1", "hello", job_id="job_ab12cd34") == 200
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["text"] == "hello"
    assert body["trigger"] == "routine"
    assert body["idempotency_key"] == "job_ab12cd34"


def test_routine_wake_without_job_id_omits_key(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Resp:
        status = 200

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    def fake_urlopen(req: Request, timeout: float | None = None) -> _Resp:
        del timeout
        captured["body"] = json.loads(req.data.decode())
        return _Resp()

    monkeypatch.setattr("artek_buddy.worker.urllib.request.urlopen", fake_urlopen)
    assert wake_routine("http://127.0.0.1:9", "tok", "bot_1", "hello") == 200
    body = captured["body"]
    assert isinstance(body, dict)
    assert "idempotency_key" not in body
