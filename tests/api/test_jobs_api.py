from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from artek_buddy.__main__ import jobs_dead
from artek_buddy.db.shaping import isoformat_utc


@pytest.fixture(autouse=True)
def clean_jobs(client) -> None:
    store = client.app.state.store
    with store._conn() as conn:
        conn.execute("DELETE FROM jobs")
        conn.commit()


def test_job_enqueue_claim_and_ack_lifecycle(client) -> None:
    store = client.app.state.store

    # 1. Enqueue job
    job = store.enqueue_job(
        job_type="test.task",
        payload={"task": "process_data", "count": 42},
        max_attempts=3,
    )
    assert job.id.startswith("job_")
    assert job.state == "queued"
    assert job.attempts == 0

    # 2. Worker 1 claims job
    claimed = store.claim_jobs(worker_id="worker_1", limit=1, lease_seconds=300)
    assert len(claimed) == 1
    c_job = claimed[0]
    assert c_job.id == job.id
    assert c_job.state == "running"
    assert c_job.lease_owner == "worker_1"
    assert c_job.attempts == 1
    assert c_job.lease_expires_at is not None

    # 3. Worker 2 cannot claim the same job while lease is active
    empty = store.claim_jobs(worker_id="worker_2", limit=1)
    assert len(empty) == 0

    # 4. Heartbeat extends lease
    ok_heartbeat = store.heartbeat_job(c_job.id, worker_id="worker_1", extend_seconds=600)
    assert ok_heartbeat is True

    # 5. Worker 1 acks the job
    ok_ack = store.ack_job(c_job.id, result={"processed": True})
    assert ok_ack is True

    # Verify final state in database
    final_job = store.get_job(c_job.id)
    assert final_job is not None
    assert final_job.state == "succeeded"
    assert final_job.result == {"processed": True}
    assert final_job.completed_at is not None
    assert final_job.lease_owner is None


def test_job_idempotency_key_deduplication(client) -> None:
    store = client.app.state.store
    idemp_key = "sync:resource_42:2026-09-07"

    # Enqueue first time
    job_1 = store.enqueue_job(
        job_type="sync.task",
        payload={"res": 42},
        idempotency_key=idemp_key,
    )

    # Enqueue second time with exact same idempotency_key
    job_2 = store.enqueue_job(
        job_type="sync.task",
        payload={"res": 42},
        idempotency_key=idemp_key,
    )

    # Must return the exact same job without creating a duplicate
    assert job_1.id == job_2.id


def test_job_lease_expiry_allows_reclaim(client) -> None:
    store = client.app.state.store

    # Enqueue job
    job = store.enqueue_job(job_type="lease.test", payload={"item": 1})

    # Worker 1 claims with expired lease (lease_seconds=0 or backdated)
    claimed = store.claim_jobs(worker_id="worker_fail", limit=1, lease_seconds=1)
    assert len(claimed) == 1

    # Force lease expiration in database
    past = isoformat_utc(datetime.now(UTC) - timedelta(seconds=10))
    with store._conn() as conn:
        conn.execute(
            "UPDATE jobs SET lease_expires_at = %s WHERE id = %s",
            (past, job.id),
        )
        conn.commit()

    # Worker 2 should successfully reclaim the abandoned job
    reclaimed = store.claim_jobs(worker_id="worker_rescue", limit=1, lease_seconds=300)
    assert len(reclaimed) == 1
    assert reclaimed[0].id == job.id
    assert reclaimed[0].lease_owner == "worker_rescue"
    assert reclaimed[0].attempts == 2


def test_job_failure_retry_and_dead_letter(client) -> None:
    store = client.app.state.store

    # Job with max_attempts = 2
    job = store.enqueue_job(job_type="flaky.task", payload={"key": "val"}, max_attempts=2)

    # Attempt 1: claim and fail with backoff
    c1 = store.claim_jobs(worker_id="w1", limit=1)[0]
    store.fail_job(c1.id, error="Transient network glitch", backoff_seconds=0.0)

    j_after_1 = store.get_job(c1.id)
    assert j_after_1 is not None
    assert j_after_1.state == "queued"
    assert j_after_1.attempts == 1
    assert j_after_1.last_error == "Transient network glitch"

    # Attempt 2: claim and fail -> should become 'dead'
    c2 = store.claim_jobs(worker_id="w2", limit=1)[0]
    assert c2.attempts == 2
    store.fail_job(c2.id, error="Terminal failure")

    j_after_2 = store.get_job(c2.id)
    assert j_after_2 is not None
    assert j_after_2.state == "dead"
    assert j_after_2.last_error == "Terminal failure"

    # Listed under dead jobs
    dead_list = store.list_dead_jobs()
    dead_ids = [d.id for d in dead_list]
    assert c2.id in dead_ids


def test_worker_run_once_migrates_routine_to_job(client, host_token) -> None:
    store = client.app.state.store

    # 1. Create active routine that is due
    bot_res = client.post(
        "/v1/bots",
        headers={"Authorization": f"Bearer {host_token}"},
        json={"name": "RoutineBot"},
    )
    bot_id = bot_res.json()["id"]

    routine = store.create_routine(
        bot_id=bot_id,
        name="HourlyPing",
        prompt="hello from routine",
        cron="* * * * *",
        active=True,
    )

    # Force next_run_at to past so it's due
    past = isoformat_utc(datetime.now(UTC) - timedelta(minutes=1))
    with store._conn() as conn:
        conn.execute("UPDATE routines SET next_run_at = %s WHERE id = %s", (past, routine.id))
        conn.commit()

    # 2. Run worker run_once
    from artek_buddy.worker import host_base, run_once

    base = host_base()
    # Execute one worker cycle
    run_once(store, base, host_token)

    # 3. Verify a routine.fire job was enqueued and executed
    with store._conn() as conn:
        rows = conn.execute(
            """
            SELECT id, job_type, resource_id, state FROM jobs
            WHERE job_type = 'routine.fire' AND resource_id = %s
            ORDER BY created_at DESC
            """,
            (routine.id,),
        ).fetchall()
        assert len(rows) >= 1
        job_row = rows[0]
        assert job_row["resource_id"] == routine.id
        assert job_row["state"] in {"succeeded", "queued", "running"}


def test_dead_jobs_api_and_cli(client, auth_header, capsys) -> None:
    store = client.app.state.store

    # Enqueue and fail a job to dead state
    job = store.enqueue_job(
        job_type="dead.test",
        payload={
            "token": "secret_token_never_leak",
            "info": "critical error on token Bearer test_secret_123",
        },
        max_attempts=1,
    )
    c = store.claim_jobs(worker_id="w", limit=1)[0]
    store.fail_job(c.id, error="Dead error with code ABCD-EFGH")

    # 1. API GET /v1/jobs/dead (owner only)
    res = client.get("/v1/jobs/dead", headers=auth_header)
    assert res.status_code == 200
    data = res.json()
    assert "jobs" in data
    dead_item = next(item for item in data["jobs"] if item["id"] == job.id)
    assert dead_item["state"] == "dead"
    # Verify secret redaction in API response
    assert "token" not in dead_item["payload"]
    assert "test_secret_123" not in str(dead_item["payload"])
    assert "[redacted]" in str(dead_item["payload"]["info"])
    assert "ABCD-EFGH" not in str(dead_item["last_error"])
    assert "[redacted]" in str(dead_item["last_error"])

    # 2. CLI jobs-dead command
    code = jobs_dead()
    assert code == 0
    cli_out = capsys.readouterr().out
    parsed = json.loads(cli_out)
    assert isinstance(parsed, list)
    cli_dead = next(item for item in parsed if item["id"] == job.id)
    assert "token" not in cli_dead["payload"]
    assert "[redacted]" in str(cli_dead["payload"]["info"])
