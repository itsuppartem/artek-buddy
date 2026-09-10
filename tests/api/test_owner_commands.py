from __future__ import annotations

import asyncio
import base64
import time
import uuid

import httpx
import pytest
from tests.api.helpers import (
    create_bot,
    simulate_host_restart,
    wait_run,
    wait_run_status,
    wait_thread_has,
)

from artek_buddy.db.shaping import UNKNOWN_OUTCOME_TEXT


def _user_texts(payload: dict) -> list[str]:
    found: list[str] = []
    for msg in payload.get("messages") or []:
        if msg.get("role") != "user":
            continue
        for block in msg.get("blocks") or []:
            if block.get("kind") == "text" and block.get("text"):
                found.append(str(block["text"]))
    return found


def test_lost_http_after_accept_reuses_command_id(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CmdLost")["id"]
    body = {"text": "hello", "command_id": "cmd_lost_hello"}
    first = client.post(f"/v1/threads/{bot_id}/messages", headers=auth_header, json=body)
    assert first.status_code == 200, first.text
    second = client.post(f"/v1/threads/{bot_id}/messages", headers=auth_header, json=body)
    assert second.status_code == 200, second.text
    assert first.json()["run_id"] == second.json()["run_id"]
    done = wait_run(client, auth_header, bot_id, first.json()["run_id"])
    assert done["run"]["status"] == "completed"
    assert _user_texts(done).count("hello") == 1


def test_same_command_id_changed_payload_is_conflict(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CmdMismatch")["id"]
    first = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello", "command_id": "cmd_mismatch"},
    )
    assert first.status_code == 200, first.text
    wait_run(client, auth_header, bot_id, first.json()["run_id"])
    changed = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "other", "command_id": "cmd_mismatch"},
    )
    assert changed.status_code == 409
    assert "different message" in changed.json()["detail"]


def test_timeout_after_run_id_is_unknown_not_a_second_send(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CmdUnknown")["id"]
    command_id = "cmd_unknown_timeout"
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-unknown-timeout", "command_id": command_id},
    )
    assert sent.status_code == 200, sent.text
    run_id = sent.json()["run_id"]
    parked = wait_run_status(client, auth_header, bot_id, run_id, "unknown")
    assert parked["run"]["status"] == "unknown"
    assert parked["run"]["status"] != "failed"
    assert parked["run"].get("error") == UNKNOWN_OUTCOME_TEXT
    listed = client.get("/v1/bots", headers=auth_header).json()["bots"]
    row = next(item for item in listed if item["id"] == bot_id)
    assert row["execution_state"] == "unconfirmed"
    retry = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-unknown-timeout", "command_id": command_id},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["run_id"] == run_id
    after = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
    assert _user_texts(after).count("please e2e-unknown-timeout") == 1


def test_new_attempt_after_unknown_is_linked_and_does_not_revive_stop(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CmdAttempt")["id"]
    first = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-unknown-timeout", "command_id": "cmd_attempt_a"},
    )
    assert first.status_code == 200, first.text
    run_id = first.json()["run_id"]
    wait_run_status(client, auth_header, bot_id, run_id, "unknown")
    nxt = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={
            "text": "hello",
            "command_id": "cmd_attempt_b",
            "parent_command_id": "cmd_attempt_a",
        },
    )
    assert nxt.status_code == 200, nxt.text
    assert nxt.json()["run_id"] != run_id
    parked = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
    del parked
    store = client.app.state.store
    leftover = store.get_run(run_id)
    assert leftover is not None
    assert leftover.status == "cancelled"
    wait_run(client, auth_header, bot_id, nxt.json()["run_id"])
    store.finish_turn(
        store.get_bot(bot_id),
        leftover,
        "late complete from unknown",
        "completed",
    )
    still = store.get_run(run_id)
    assert still is not None
    assert still.status == "cancelled"
    wait_thread_has(client, auth_header, bot_id, "ok")
    found = store.get_owner_command(bot_id, "cmd_attempt_b")
    assert found is not None
    assert found.parent_command_id == "cmd_attempt_a"


def test_stop_during_unknown_rejects_late_complete(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CmdStop")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-unknown-timeout", "command_id": "cmd_stop_unk"},
    )
    assert sent.status_code == 200, sent.text
    run_id = sent.json()["run_id"]
    wait_run_status(client, auth_header, bot_id, run_id, "unknown")
    stopped = client.post(f"/v1/threads/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200, stopped.text
    store = client.app.state.store
    leftover = store.get_run(run_id)
    assert leftover is not None
    assert leftover.status == "cancelled"
    store.finish_turn(
        store.get_bot(bot_id),
        leftover,
        "late complete from unknown",
        "completed",
    )
    still = store.get_run(run_id)
    assert still is not None
    assert still.status == "cancelled"


def _record_dispatches(monkeypatch) -> list[str]:
    from artek_buddy.http import turns

    executions: list[str] = []

    async def record(*args, **kwargs) -> None:
        run = kwargs.get("run") or args[5]
        executions.append(run.id)

    monkeypatch.setattr(turns, "_run_turn", record)
    return executions


def _rendezvous_ensure_agent(monkeypatch, count: int) -> None:
    from artek_buddy.http import turns

    original = turns._ensure_agent
    arrived = {"n": 0}
    lock = asyncio.Lock()
    release = asyncio.Event()

    async def rendezvous(history, rt, bot):
        result = await original(history, rt, bot)
        async with lock:
            arrived["n"] += 1
            if arrived["n"] >= count:
                release.set()
        await asyncio.wait_for(release.wait(), timeout=10)
        return result

    monkeypatch.setattr(turns, "_ensure_agent", rendezvous)


async def _post_messages_together(client, auth_header, bot_id: str, bodies: list[dict]) -> list:
    transport = httpx.ASGITransport(app=client.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as session:
        return list(
            await asyncio.gather(
                *[
                    session.post(
                        f"/v1/threads/{bot_id}/messages",
                        headers=auth_header,
                        json=body,
                    )
                    for body in bodies
                ]
            )
        )


def _wait_dispatches(executions: list[str], expected: int, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(executions) == expected:
            return
        time.sleep(0.05)
    raise AssertionError(f"expected {expected} dispatches, got {executions}")


@pytest.mark.asyncio
async def test_twenty_identical_commands_dispatch_once(client, auth_header, monkeypatch) -> None:
    bot_id = create_bot(client, auth_header, "CmdOnce")["id"]
    executions = _record_dispatches(monkeypatch)
    _rendezvous_ensure_agent(monkeypatch, 20)
    body = {"text": "synthetic task", "command_id": f"cmd_{uuid.uuid4()}"}
    replies = await _post_messages_together(client, auth_header, bot_id, [body] * 20)
    assert all(item.status_code == 200 for item in replies), [item.text for item in replies]
    run_ids = {item.json()["run_id"] for item in replies}
    assert len(run_ids) == 1
    _wait_dispatches(executions, 1)
    thread = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
    assert _user_texts(thread).count("synthetic task") == 1


@pytest.mark.asyncio
async def test_changed_payload_conflicts_without_a_second_dispatch(
    client, auth_header, monkeypatch
) -> None:
    bot_id = create_bot(client, auth_header, "CmdConflictRace")["id"]
    executions = _record_dispatches(monkeypatch)
    _rendezvous_ensure_agent(monkeypatch, 2)
    command_id = f"cmd_{uuid.uuid4()}"
    replies = await _post_messages_together(
        client,
        auth_header,
        bot_id,
        [
            {"text": "hello", "command_id": command_id},
            {"text": "other", "command_id": command_id},
        ],
    )
    codes = sorted(item.status_code for item in replies)
    assert codes == [200, 409], [item.text for item in replies]
    conflict = next(item for item in replies if item.status_code == 409)
    assert "different message" in conflict.json()["detail"]
    _wait_dispatches(executions, 1)
    thread = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
    assert len(_user_texts(thread)) == 1


def test_crash_before_dispatch_retry_starts_once(client, auth_header, monkeypatch) -> None:
    from artek_buddy.db.history.turns import TurnsMixin

    bot_id = create_bot(client, auth_header, "CmdCrash")["id"]
    executions = _record_dispatches(monkeypatch)
    real = TurnsMixin.claim_turn_dispatch
    seen = {"n": 0}

    def crash_first(self, run_id: str) -> bool:
        seen["n"] += 1
        if seen["n"] == 1:
            return False
        return real(self, run_id)

    monkeypatch.setattr(TurnsMixin, "claim_turn_dispatch", crash_first)
    body = {"text": "hello", "command_id": "cmd_crash_hello"}
    first = client.post(f"/v1/threads/{bot_id}/messages", headers=auth_header, json=body)
    assert first.status_code == 200, first.text
    assert executions == []
    second = client.post(f"/v1/threads/{bot_id}/messages", headers=auth_header, json=body)
    assert second.status_code == 200, second.text
    assert first.json()["run_id"] == second.json()["run_id"]
    _wait_dispatches(executions, 1)
    thread = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
    assert _user_texts(thread).count("hello") == 1


def test_restart_before_claim_does_not_park_or_duplicate(client, auth_header, monkeypatch) -> None:
    from artek_buddy.db.history.turns import TurnsMixin

    bot_id = create_bot(client, auth_header, "CmdRestartPending")["id"]
    executions = _record_dispatches(monkeypatch)
    real = TurnsMixin.claim_turn_dispatch
    seen = {"n": 0}

    def crash_first(self, run_id: str) -> bool:
        seen["n"] += 1
        if seen["n"] == 1:
            return False
        return real(self, run_id)

    monkeypatch.setattr(TurnsMixin, "claim_turn_dispatch", crash_first)
    body = {"text": "hello", "command_id": "cmd_restart_pending"}
    first = client.post(f"/v1/threads/{bot_id}/messages", headers=auth_header, json=body)
    assert first.status_code == 200, first.text
    run_id = first.json()["run_id"]
    simulate_host_restart(client)
    parked = client.app.state.store.get_run(run_id)
    assert parked is not None
    assert parked.status == "running"
    assert parked.status != "waiting_recovery"
    retry = client.post(f"/v1/threads/{bot_id}/messages", headers=auth_header, json=body)
    assert retry.status_code == 200, retry.text
    assert retry.json()["run_id"] == run_id
    _wait_dispatches(executions, 1)


@pytest.mark.asyncio
async def test_stop_owns_the_task_after_duplicate_command_posts(
    client, auth_header, monkeypatch
) -> None:
    bot_id = create_bot(client, auth_header, "CmdStopDup")["id"]
    _rendezvous_ensure_agent(monkeypatch, 5)
    body = {"text": "please e2e-slow now", "command_id": "cmd_stop_dup"}
    replies = await _post_messages_together(client, auth_header, bot_id, [body] * 5)
    assert all(item.status_code == 200 for item in replies), [item.text for item in replies]
    run_ids = {item.json()["run_id"] for item in replies}
    assert len(run_ids) == 1
    run_id = next(iter(run_ids))
    stopped = client.post(f"/v1/threads/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200, stopped.text
    snap = wait_run(client, auth_header, bot_id, run_id)
    assert snap["run"]["status"] == "cancelled"
    thread = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
    assert _user_texts(thread).count("please e2e-slow now") == 1
    leftover = client.app.state.active_turns.get(bot_id, {})
    live = leftover.get(run_id)
    assert live is None or live.done()


def test_same_command_id_changed_attachment_bytes_is_conflict(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CmdAttachBytes")["id"]
    command_id = "cmd_attach_bytes"
    first = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={
            "text": "read it",
            "command_id": command_id,
            "attachments": [
                {
                    "name": "report.txt",
                    "content_base64": base64.b64encode(b"one").decode("ascii"),
                }
            ],
        },
    )
    assert first.status_code == 200, first.text
    wait_run(client, auth_header, bot_id, first.json()["run_id"])
    changed = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={
            "text": "read it",
            "command_id": command_id,
            "attachments": [
                {
                    "name": "report.txt",
                    "content_base64": base64.b64encode(b"two").decode("ascii"),
                }
            ],
        },
    )
    assert changed.status_code == 409
    assert "different message" in changed.json()["detail"]


def test_same_command_id_same_attachment_bytes_replays(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CmdAttachReplay")["id"]
    body = {
        "text": "read it",
        "command_id": "cmd_attach_replay",
        "attachments": [
            {
                "name": "report.txt",
                "content_base64": base64.b64encode(b"one").decode("ascii"),
            }
        ],
    }
    first = client.post(f"/v1/threads/{bot_id}/messages", headers=auth_header, json=body)
    assert first.status_code == 200, first.text
    second = client.post(f"/v1/threads/{bot_id}/messages", headers=auth_header, json=body)
    assert second.status_code == 200, second.text
    assert first.json()["run_id"] == second.json()["run_id"]
    done = wait_run(client, auth_header, bot_id, first.json()["run_id"])
    assert done["run"]["status"] == "completed"
    assert _user_texts(done).count("read it") == 1

