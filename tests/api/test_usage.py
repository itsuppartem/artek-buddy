from __future__ import annotations

import json
import time

from tests.api.helpers import create_bot, wait_run, wait_run_status, wait_thread_has

from artek_buddy.db.shaping import new_id
from artek_buddy.http.usage_persist import persist_product_usage
from artek_buddy.runtime.token_usage import (
    SCRIPTED_LEAD_USAGE,
    SCRIPTED_WORKER_USAGE,
    TokenUsage,
)

WORKER_SUMMARY = "The background job is done."
CURSOR_CONNECT_KEY = "sk-test-usage-fast-wxyz"
# cursor grok-4.6 Fast vs standard rate cards (same counts as #548).
GROK_FAST_USD = 0.577576
GROK_STANDARD_USD = 0.288788
GROK_USAGE = TokenUsage(
    input_tokens=128700,
    output_tokens=1242,
    cache_read_tokens=47872,
    total_tokens=177814,
    provider="cursor",
    model="grok-4.6",
)


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
    assert "estimated_cost_usd" not in row
    assert "estimated_cost_usd" not in totals


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
    assert lead_row["run_id"] != worker_row["run_id"]
    assert lead_row["input_tokens"] == SCRIPTED_LEAD_USAGE.input_tokens
    assert worker_row["input_tokens"] == SCRIPTED_WORKER_USAGE.input_tokens
    lead_summary = client.get(
        "/v1/usage/summary",
        headers=auth_header,
        params={"bot_id": bot_id, "run_id": lead_id},
    )
    assert lead_summary.status_code == 200
    assert lead_summary.json()["runs"] == 1
    assert lead_summary.json()["total_tokens"] == SCRIPTED_LEAD_USAGE.total_tokens
    worker_summary = client.get(
        "/v1/usage/summary",
        headers=auth_header,
        params={"bot_id": bot_id, "run_id": worker_id},
    )
    assert worker_summary.status_code == 200
    assert worker_summary.json()["runs"] == 1
    assert worker_summary.json()["total_tokens"] == SCRIPTED_WORKER_USAGE.total_tokens
    listed = client.get("/v1/usage", headers=auth_header, params={"bot_id": bot_id})
    assert listed.status_code == 200
    run_ids = {item["run_id"] for item in listed.json()["records"]}
    assert lead_id in run_ids
    assert worker_id in run_ids
    summary = client.get(
        "/v1/usage/summary",
        headers=auth_header,
        params={"bot_id": bot_id},
    )
    assert summary.status_code == 200
    assert summary.json()["runs"] >= 2
    assert "estimated_cost_usd" not in lead_row
    assert "estimated_cost_usd" not in worker_row
    assert "estimated_cost_usd" not in summary.json()


def test_usage_persists_estimated_cost_for_grok_fast(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "UsageCostFast")["id"]
    run_id = new_id("run")
    store = client.app.state.store
    stored = store.record_usage(
        bot_id=bot_id,
        run_id=run_id,
        provider="cursor",
        model="grok-4.6",
        input_tokens=128700,
        output_tokens=1242,
        cache_read_tokens=47872,
        cache_write_tokens=0,
        reasoning_tokens=0,
        total_tokens=177814,
        fast=True,
    )
    assert stored is not None
    assert stored.estimated_cost_usd == 0.577576
    listed = client.get(
        "/v1/usage",
        headers=auth_header,
        params={"bot_id": bot_id, "run_id": run_id},
    )
    assert listed.status_code == 200
    records = listed.json()["records"]
    assert len(records) == 1
    row = records[0]
    assert row["input_tokens"] == 128700
    assert row["output_tokens"] == 1242
    assert row["cache_read_tokens"] == 47872
    assert row["total_tokens"] == 177814
    assert row["estimated_cost_usd"] == 0.577576
    summary = client.get(
        "/v1/usage/summary",
        headers=auth_header,
        params={"bot_id": bot_id, "run_id": run_id},
    )
    assert summary.status_code == 200
    assert summary.json()["estimated_cost_usd"] == 0.577576
    assert summary.json()["runs"] == 1


def test_usage_standard_cost_when_fast_is_off(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "UsageCostStd")["id"]
    run_id = new_id("run")
    store = client.app.state.store
    store.record_usage(
        bot_id=bot_id,
        run_id=run_id,
        provider="cursor",
        model="grok-4.6",
        input_tokens=128700,
        output_tokens=1242,
        cache_read_tokens=47872,
        total_tokens=177814,
        fast=False,
    )
    listed = client.get(
        "/v1/usage",
        headers=auth_header,
        params={"bot_id": bot_id, "run_id": run_id},
    )
    assert listed.status_code == 200
    row = listed.json()["records"][0]
    assert row["estimated_cost_usd"] == 0.288788


def test_usage_unknown_model_omits_estimated_cost(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "UsageCostUnknown")["id"]
    run_id = new_id("run")
    store = client.app.state.store
    store.record_usage(
        bot_id=bot_id,
        run_id=run_id,
        provider="cursor",
        model="mystery-model",
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        fast=True,
    )
    listed = client.get(
        "/v1/usage",
        headers=auth_header,
        params={"bot_id": bot_id, "run_id": run_id},
    )
    assert listed.status_code == 200
    row = listed.json()["records"][0]
    assert row["input_tokens"] == 100
    assert "estimated_cost_usd" not in row
    summary = client.get(
        "/v1/usage/summary",
        headers=auth_header,
        params={"bot_id": bot_id, "run_id": run_id},
    )
    assert summary.status_code == 200
    assert "estimated_cost_usd" not in summary.json()


def _connect_cursor(client, auth_header: dict[str, str]) -> None:
    connected = client.post(
        "/v1/models/credentials",
        headers=auth_header,
        json={"provider": "cursor", "api_key": CURSOR_CONNECT_KEY},
    )
    assert connected.status_code == 200


def _set_cursor_fast(client, auth_header: dict[str, str], *, fast: bool, bot_id: str) -> None:
    chosen = client.post(
        "/v1/models/default",
        headers=auth_header,
        json={
            "provider": "cursor",
            "model": "scripted",
            "effort": "xhigh",
            "fast": fast,
            "bot_id": bot_id,
        },
    )
    assert chosen.status_code == 200, chosen.text


def _persist_grok_and_row(client, auth_header: dict[str, str], bot_id: str, run_id: str) -> dict:
    store = client.app.state.store
    bot = store.get_bot(bot_id)
    assert bot is not None
    persist_product_usage(store, client.app.state.hub, bot, run_id, GROK_USAGE)
    listed = client.get(
        "/v1/usage",
        headers=auth_header,
        params={"bot_id": bot_id, "run_id": run_id},
    )
    assert listed.status_code == 200, listed.text
    records = listed.json()["records"]
    assert len(records) == 1
    return records[0]


def _usage_recorded_payloads(client, bot_id: str, run_id: str) -> list[dict]:
    return [
        event.payload
        for event in client.app.state.hub.replay(bot_id)
        if event.type.value == "usage.recorded" and event.run_id == run_id
    ]


def test_grok_fast_estimate_uses_fast_bound_at_run_start(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "UsageFastStart")["id"]
    store = client.app.state.store
    bot = store.get_bot(bot_id)
    assert bot is not None
    store.set_default_model("cursor", "grok-4.6", fast=True)
    run = store.begin_run(bot, model_provider="cursor", model_id="grok-4.6")
    store.set_default_model("cursor", "grok-4.6", fast=False)
    persist_product_usage(store, client.app.state.hub, bot, run.id, GROK_USAGE)
    listed = client.get(
        "/v1/usage",
        headers=auth_header,
        params={"bot_id": bot_id, "run_id": run.id},
    )
    assert listed.status_code == 200
    row = listed.json()["records"][0]
    assert row["estimated_cost_usd"] == GROK_FAST_USD
    recorded = _usage_recorded_payloads(client, bot_id, run.id)
    assert recorded
    last = recorded[-1]
    assert last["estimated_cost_usd"] == GROK_FAST_USD
    blob = json.dumps(last)
    assert "api_key" not in blob
    assert CURSOR_CONNECT_KEY not in blob
    assert "test-secret-seed" not in blob


def test_grok_standard_estimate_not_rewritten_when_fast_turned_on(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "UsageStdStart")["id"]
    store = client.app.state.store
    bot = store.get_bot(bot_id)
    assert bot is not None
    store.set_default_model("cursor", "grok-4.6", fast=False)
    run = store.begin_run(bot, model_provider="cursor", model_id="grok-4.6")
    store.set_default_model("cursor", "grok-4.6", fast=True)
    persist_product_usage(store, None, bot, run.id, GROK_USAGE)
    listed = client.get(
        "/v1/usage",
        headers=auth_header,
        params={"bot_id": bot_id, "run_id": run.id},
    )
    assert listed.status_code == 200
    assert listed.json()["records"][0]["estimated_cost_usd"] == GROK_STANDARD_USD


def test_usage_keeps_grok_fast_card_when_fast_unchecked_during_e2e_slow(
    client, auth_header
) -> None:
    _connect_cursor(client, auth_header)
    bot_id = create_bot(client, auth_header, "UsageFastLive")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-slow now"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    wait_run_status(client, auth_header, bot_id, run_id, "running")
    _set_cursor_fast(client, auth_header, fast=False, bot_id=bot_id)
    snap = wait_run(client, auth_header, bot_id, run_id)
    assert snap["run"]["status"] == "completed"
    row = _persist_grok_and_row(client, auth_header, bot_id, run_id)
    assert row["estimated_cost_usd"] == GROK_FAST_USD
    recorded = _usage_recorded_payloads(client, bot_id, run_id)
    assert recorded
    blob = json.dumps(recorded)
    assert "api_key" not in blob
    assert CURSOR_CONNECT_KEY not in blob
    assert any(item.get("estimated_cost_usd") == GROK_FAST_USD for item in recorded)


def test_usage_keeps_grok_standard_card_when_fast_checked_during_e2e_slow(
    client, auth_header
) -> None:
    _connect_cursor(client, auth_header)
    bot_id = create_bot(client, auth_header, "UsageStdLive")["id"]
    _set_cursor_fast(client, auth_header, fast=False, bot_id=bot_id)
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-slow now"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    wait_run_status(client, auth_header, bot_id, run_id, "running")
    _set_cursor_fast(client, auth_header, fast=True, bot_id=bot_id)
    snap = wait_run(client, auth_header, bot_id, run_id)
    assert snap["run"]["status"] == "completed"
    row = _persist_grok_and_row(client, auth_header, bot_id, run_id)
    assert row["estimated_cost_usd"] == GROK_STANDARD_USD
