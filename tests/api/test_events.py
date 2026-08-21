from __future__ import annotations

import asyncio

import httpx

from tests.api.helpers import create_bot, wait_run


def _sse_open(app, path: str, headers: dict[str, str], needle: str | None = None) -> tuple[int, str, str]:
    """Read SSE without TestClient.stream, which deadlocks on the infinite generator."""

    async def _run() -> tuple[int, str, str]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=5.0) as ac:
            async with ac.stream("GET", path, headers=headers) as response:
                ctype = response.headers.get("content-type", "")
                buf = ""
                if needle is None:
                    return response.status_code, ctype, buf
                async for chunk in response.aiter_text():
                    buf += chunk
                    if needle in buf:
                        return response.status_code, ctype, buf
                raise AssertionError(f"SSE did not include {needle!r}: {buf!r}")

    async def _bounded() -> tuple[int, str, str]:
        return await asyncio.wait_for(_run(), timeout=8)

    return asyncio.run(_bounded())


def test_workspace_events_is_sse_and_does_not_hang(client, auth_header) -> None:
    status, ctype, body = _sse_open(client.app, "/v1/events", auth_header, needle=":")
    assert status == 200
    assert "text/event-stream" in ctype
    assert ":" in body


def test_thread_events_replay_message_created(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "SseReplay")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    status, ctype, body = _sse_open(
        client.app,
        f"/v1/threads/{bot_id}/events",
        auth_header,
        needle="thread.message.created",
    )
    assert status == 200
    assert "text/event-stream" in ctype
    assert "thread.message.created" in body


def test_thread_events_missing_bot_is_404(client, auth_header) -> None:
    response = client.get("/v1/threads/bot_missing/events", headers=auth_header)
    assert response.status_code == 404
