from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def sse_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, postgres_ok: None, host_token: str):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("AGENT_DATA_DIR", str(data))
    monkeypatch.setenv("AGENT_CWD", str(tmp_path / "workspace"))
    monkeypatch.setenv("AGENT_RUNTIME", "scripted")
    monkeypatch.setenv("SANDBOX_PROVIDER", "fake")
    monkeypatch.setenv("CURSOR_API_KEY", "")
    monkeypatch.setenv("AGENT_HTTP_TOKEN", host_token)
    monkeypatch.chdir(tmp_path)
    from artek_buddy.main import app

    return app


@asynccontextmanager
async def _http(app):
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=8.0) as ac:
            yield ac


async def _wait_run(ac: httpx.AsyncClient, headers: dict[str, str], bot_id: str, run_id: str) -> dict:
    deadline = time.time() + 15
    last: dict = {}
    while time.time() < deadline:
        snap = await ac.get(f"/v1/threads/{bot_id}", headers=headers)
        assert snap.status_code == 200, snap.text
        last = snap.json()
        run = last.get("run") or {}
        if run.get("id") == run_id and run.get("status") in {"completed", "failed", "cancelled"}:
            return last
        await asyncio.sleep(0.1)
    raise AssertionError(f"turn {run_id} did not finish: {last.get('run')}")


async def test_workspace_events_is_sse_and_does_not_hang(sse_app, auth_header) -> None:
    async with _http(sse_app) as ac:
        async with ac.stream("GET", "/v1/events", headers=auth_header) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            buf = ""
            async for chunk in response.aiter_text():
                buf += chunk
                if ":" in buf:
                    break
            else:
                raise AssertionError("SSE opened without a keepalive frame")


async def test_thread_events_replay_message_created(sse_app, auth_header) -> None:
    async with _http(sse_app) as ac:
        created = await ac.post("/v1/bots", headers=auth_header, json={"name": "SseReplay"})
        assert created.status_code == 200, created.text
        bot_id = created.json()["id"]
        sent = await ac.post(
            f"/v1/threads/{bot_id}/messages",
            headers=auth_header,
            json={"text": "hello"},
        )
        assert sent.status_code == 200, sent.text
        await _wait_run(ac, auth_header, bot_id, sent.json()["run_id"])
        async with ac.stream("GET", f"/v1/threads/{bot_id}/events", headers=auth_header) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            buf = ""
            async for chunk in response.aiter_text():
                buf += chunk
                if "thread.message.created" in buf:
                    break
            else:
                raise AssertionError("replay did not include thread.message.created")


def test_thread_events_missing_bot_is_404(client, auth_header) -> None:
    response = client.get("/v1/threads/bot_missing/events", headers=auth_header)
    assert response.status_code == 404
