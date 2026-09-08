from __future__ import annotations

import time

from tests.api.helpers import create_bot, wait_run, wait_thread_has

from artek_buddy.runtime.token_usage import SCRIPTED_LEAD_USAGE, SCRIPTED_WORKER_USAGE

WORKER_SUMMARY = "The background job is done."


def _wait_usage_row(client, auth_header: dict[str, str], bot_id: str, run_id: str) -> dict:
    deadline = time.time() + 5.0
    last: dict = {}
    while time.time() < deadline:
        listed = client.get(
            "/v1/usage",
            headers=auth_header,
            params={"bot_id": bot_id, "run_id": run_id},
        )
        assert listed.status_code == 200, listed.text
        last = listed.json()
        records = last.get("records") or []
        if records:
            return records[0]
        time.sleep(0.05)
    raise AssertionError(f"no usage row for {run_id}: {last}")


def test_usage_requires_auth(client) -> None:
    missing = client.get("/v1/usage")
    assert missing.status_code == 401
    missing_summary = client.get("/v1/usage/summary")
    assert missing_summary.status_code == 401
    bad = {"Authorization": "Bearer nope"}
    refused = client.get("/v1/usage", headers=bad)
    assert refused.status_code == 403
    refused_summary = client.get("/v1/usage/summary", headers=bad)
    assert refused_summary.status_code == 403


def test_usage_missing_bot_is_404(client, auth_header) -> None:
    listed = client.get("/v1/usage", headers=auth_header, params={"bot_id": "bot_missing"})
    assert listed.status_code == 404
    summary = client.get(
        "/v1/usage/summary",
        headers=auth_header,
        params={"bot_id": "bot_missing"},
    )
    assert summary.status_code == 404


def test_completed_scripted_run_persists_usage(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "UsageLead")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    snap = wait_run(client, auth_header, bot_id, run_id)
    assert snap["run"]["status"] == "completed"
    row = _wait_usage_row(client, auth_header, bot_id, run_id)
    assert row["bot_id"] == bot_id
    assert row["run_id"] == run_id
    assert row["provider"] == "scripted"
    assert row["input_tokens"] == SCRIPTED_LEAD_USAGE.input_tokens
    assert row["output_tokens"] == SCRIPTED_LEAD_USAGE.output_tokens
    assert row["cache_read_tokens"] == SCRIPTED_LEAD_USAGE.cache_read_tokens
    assert row["cache_write_tokens"] == SCRIPTED_LEAD_USAGE.cache_write_tokens
    assert row["reasoning_tokens"] == SCRIPTED_LEAD_USAGE.reasoning_tokens
    assert row["total_tokens"] == SCRIPTED_LEAD_USAGE.total_tokens
    summary = client.get(
        "/v1/usage/summary",
        headers=auth_header,
        params={"bot_id": bot_id},
    )
    assert summary.status_code == 200
    totals = summary.json()
    assert totals["input_tokens"] == SCRIPTED_LEAD_USAGE.input_tokens
    assert totals["output_tokens"] == SCRIPTED_LEAD_USAGE.output_tokens
    assert totals["cache_read_tokens"] == SCRIPTED_LEAD_USAGE.cache_read_tokens
    assert totals["cache_write_tokens"] == SCRIPTED_LEAD_USAGE.cache_write_tokens
    assert totals["reasoning_tokens"] == SCRIPTED_LEAD_USAGE.reasoning_tokens
    assert totals["total_tokens"] == SCRIPTED_LEAD_USAGE.total_tokens
    assert totals["runs"] == 1


def test_missing_usage_does_not_fail_the_turn(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "UsageMissing")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-no-usage"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    snap = wait_run(client, auth_header, bot_id, run_id)
    assert snap["run"]["status"] == "completed"
    listed = client.get(
        "/v1/usage",
        headers=auth_header,
        params={"bot_id": bot_id, "run_id": run_id},
    )
    assert listed.status_code == 200
    assert listed.json()["records"] == []
    fail = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-fail now"},
    )
    assert fail.status_code == 200
    fail_id = fail.json()["run_id"]
    failed = wait_run(client, auth_header, bot_id, fail_id)
    assert failed["run"]["status"] == "failed"
    empty = client.get(
        "/v1/usage",
        headers=auth_header,
        params={"bot_id": bot_id, "run_id": fail_id},
    )
    assert empty.status_code == 200
    assert empty.json()["records"] == []


def test_worker_usage_run_id_is_distinct_from_lead(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "UsageWorker")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-background-worker-chat"},
    )
    assert sent.status_code == 200
    lead_id = sent.json()["run_id"]
    snap = wait_run(client, auth_header, bot_id, lead_id)
    assert snap["run"]["status"] == "completed"
    workers = client.get(f"/v1/bots/{bot_id}/subagents", headers=auth_header)
    assert workers.status_code == 200
    live = workers.json()["subagents"]
    assert live
    worker_id = live[0]["id"]
    assert worker_id != lead_id
    wait_thread_has(client, auth_header, bot_id, WORKER_SUMMARY, timeout=20)
    lead_row = _wait_usage_row(client, auth_header, bot_id, lead_id)
    worker_row = _wait_usage_row(client, auth_header, bot_id, worker_id)
    assert lead_row["run_id"] == lead_id
    assert worker_row["run_id"] == worker_id
    assert lead_row["input_tokens"] == SCRIPTED_LEAD_USAGE.input_tokens
    assert worker_row["input_tokens"] == SCRIPTED_WORKER_USAGE.input_tokens
    summary = client.get(
        "/v1/usage/summary",
        headers=auth_header,
        params={"bot_id": bot_id},
    )
    assert summary.status_code == 200
    totals = summary.json()
    assert totals["runs"] == 2
    assert totals["input_tokens"] == (
        SCRIPTED_LEAD_USAGE.input_tokens + SCRIPTED_WORKER_USAGE.input_tokens
    )
    assert totals["output_tokens"] == (
        SCRIPTED_LEAD_USAGE.output_tokens + SCRIPTED_WORKER_USAGE.output_tokens
    )
    assert totals["total_tokens"] == (
        SCRIPTED_LEAD_USAGE.total_tokens + SCRIPTED_WORKER_USAGE.total_tokens
    )
