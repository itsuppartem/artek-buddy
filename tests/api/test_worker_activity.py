from __future__ import annotations

import time

from tests.api.helpers import create_bot, message_texts, wait_run

from artek_buddy.runtime.scripted import (
    E2E_SUBAGENT_NAME,
    E2E_WORKER_ACK,
    E2E_WORKER_STATUS,
)
from artek_buddy.runtime.tools.product import ProductTools
from artek_buddy.runtime.types import TurnContext


def _workers(client, auth_header: dict[str, str], bot_id: str) -> list[dict]:
    listed = client.get(f"/v1/bots/{bot_id}/subagents", headers=auth_header)
    assert listed.status_code == 200, listed.text
    return listed.json()["subagents"]


def _wait_activity(client, auth_header: dict[str, str], bot_id: str, minimum: int) -> dict:
    deadline = time.time() + 12
    last: list[dict] = []
    while time.time() < deadline:
        last = _workers(client, auth_header, bot_id)
        if last and int(last[0].get("activity_seq") or 0) >= minimum:
            return last[0]
        time.sleep(0.1)
    raise AssertionError(f"activity_seq never reached {minimum}: {last}")


def test_no_text_worker_keeps_host_activity_and_survives_status(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "ActivityLead")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-activity-no-text"},
    )
    assert sent.status_code == 200
    snap = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert E2E_WORKER_ACK in message_texts(snap)
    worker = _wait_activity(client, auth_header, bot_id, 20)
    worker_id = worker["id"]
    assert not (worker.get("progress") or "").strip()
    assert worker["status"] == "running"
    assert worker.get("last_activity_kind") in {"tool_started", "tool_finished", "run_started"}
    assert worker.get("last_activity_at")

    status = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-status"},
    )
    assert status.status_code == 200
    status_snap = wait_run(client, auth_header, bot_id, status.json()["run_id"])
    assert E2E_WORKER_STATUS in message_texts(status_snap)
    after = _workers(client, auth_header, bot_id)[0]
    assert after["id"] == worker_id
    assert after["status"] == "running"


def test_status_false_idle_stop_is_rejected(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "FalseIdle")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-activity-no-text"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    worker = _wait_activity(client, auth_header, bot_id, 20)
    worker_id = worker["id"]

    ping = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-false-idle"},
    )
    assert ping.status_code == 200
    ping_snap = wait_run(client, auth_header, bot_id, ping.json()["run_id"])
    assert E2E_WORKER_STATUS in message_texts(ping_snap)
    after = _workers(client, auth_header, bot_id)[0]
    assert after["id"] == worker_id
    assert after["status"] == "running"


def test_stale_activity_seq_rejects_model_stop(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "StaleStop")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-activity-no-text"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    worker = _wait_activity(client, auth_header, bot_id, 20)
    worker_id = worker["id"]

    ping = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-stale-stop"},
    )
    assert ping.status_code == 200
    wait_run(client, auth_header, bot_id, ping.json()["run_id"])
    after = _workers(client, auth_header, bot_id)[0]
    assert after["id"] == worker_id
    assert after["status"] == "running"


def test_inspect_omits_reasoning_and_names_empty_progress(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "InspectActivity")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-activity-no-text"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    _wait_activity(client, auth_header, bot_id, 20)
    runtime = client.app.state.runtime
    bot = client.app.state.store.get_bot(bot_id)
    assert bot is not None
    runtime.set_current_turn_context(bot.id, "run_inspect", bot.thread_id, role="lead")
    tools = ProductTools(runtime)
    inspected = tools.execute(
        "inspect_subagent",
        {"ref": E2E_SUBAGENT_NAME},
        bound_bot_id=bot.id,
    )
    assert inspected["ok"] is True
    assert inspected["text_update"] == "no text update"
    assert inspected["progress_empty"] is True
    assert "thinking" not in inspected
    assert inspected["activity_seq"] >= 20
    assert "idle" not in str(inspected).lower()


def test_matching_inspect_seq_stops_when_no_tool_is_running(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CasStop")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-activity-no-text"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    worker = _wait_activity(client, auth_header, bot_id, 20)
    deadline = time.time() + 5
    while time.time() < deadline and worker.get("tool_running"):
        time.sleep(0.1)
        worker = _workers(client, auth_header, bot_id)[0]
    assert worker.get("tool_running") is False
    runtime = client.app.state.runtime
    bot = client.app.state.store.get_bot(bot_id)
    assert bot is not None
    runtime.set_current_turn_context(bot.id, "run_cas", bot.thread_id, role="lead")
    runtime.set_owner_intent("run_cas", "other")
    tools = ProductTools(runtime)
    stopped = tools.execute(
        "stop_subagent",
        {"ref": worker["id"], "inspected_activity_seq": worker["activity_seq"]},
        bound_bot_id=bot.id,
    )
    assert stopped["ok"] is True, stopped
    assert stopped["status"] == "cancelled"
    assert _workers(client, auth_header, bot_id)[0]["status"] == "cancelled"


def test_owner_stop_blocks_later_worker_callbacks(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CancelGate")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-activity-no-text"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    worker = _wait_activity(client, auth_header, bot_id, 1)
    worker_id = worker["id"]
    stopped = client.post(
        f"/v1/bots/{bot_id}/subagents/{worker_id}/stop",
        headers=auth_header,
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "cancelled"
    runtime = client.app.state.runtime
    bot = client.app.state.store.get_bot(bot_id)
    assert bot is not None
    tools = ProductTools(runtime)
    refused = tools.execute(
        "list_subagents",
        {},
        bound_bot_id=bot.id,
        turn=TurnContext(
            bot_id=bot.id,
            run_id=worker_id,
            thread_id=bot.thread_id,
            role="subagent",
        ),
    )
    assert refused["ok"] is False
    assert "cancelled" in str(refused.get("error") or "")
