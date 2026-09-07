from __future__ import annotations

from artek_buddy.jobs import (
    JobRecord,
    calculate_backoff_seconds,
    sanitize_job_payload,
)


def test_calculate_backoff_with_jitter() -> None:
    # First attempt: base is 10.0, with +/-15% jitter it should be between 8.5 and 11.5
    for _ in range(20):
        b1 = calculate_backoff_seconds(1, base=10.0, max_backoff=300.0, jitter=True)
        assert 8.0 <= b1 <= 12.0

    # Without jitter: strictly deterministic exponential
    assert calculate_backoff_seconds(1, base=10.0, max_backoff=300.0, jitter=False) == 10.0
    assert calculate_backoff_seconds(2, base=10.0, max_backoff=300.0, jitter=False) == 20.0
    assert calculate_backoff_seconds(3, base=10.0, max_backoff=300.0, jitter=False) == 40.0
    assert calculate_backoff_seconds(4, base=10.0, max_backoff=300.0, jitter=False) == 80.0
    assert calculate_backoff_seconds(10, base=10.0, max_backoff=300.0, jitter=False) == 300.0


def test_sanitize_job_payload_omits_secrets_and_redacts_tokens() -> None:
    payload = {
        "bot_id": "bot_123",
        "prompt": "Run check with Bearer secret_bearer_token and token dev_792362ff782216c7",
        "token": "sensitive_token_abc",
        "password": "secret_password",
        "nested": {
            "key": "forbidden_key",
            "safe_text": "postgresql://artek:pass@127.0.0.1:5432/db with code ABCD-EFGH",
        },
    }
    sanitized = sanitize_job_payload(payload)

    # Forbidden keys stripped entirely
    assert "token" not in sanitized
    assert "password" not in sanitized
    assert "key" not in sanitized["nested"]

    # Sensitive values in strings redacted
    assert "secret_bearer_token" not in sanitized["prompt"]
    assert "dev_792362ff782216c7" not in sanitized["prompt"]
    assert "[redacted]" in sanitized["prompt"]

    assert "pass" not in sanitized["nested"]["safe_text"]
    assert "ABCD-EFGH" not in sanitized["nested"]["safe_text"]
    assert "[redacted]" in sanitized["nested"]["safe_text"]

    assert sanitized["bot_id"] == "bot_123"


def test_job_record_to_dict_redaction() -> None:
    record = JobRecord(
        id="job_1",
        job_type="routine.fire",
        resource_id="rtn_1",
        idempotency_key="routine:rtn_1:run_1",
        state="dead",
        payload={
            "token": "secret_token_123",
            "prompt": "please test with code WXYZ-2345",
        },
        result=None,
        last_error="Failed with Bearer secret_bearer_error",
        attempts=5,
        max_attempts=5,
        lease_owner=None,
        lease_expires_at=None,
        run_at="2026-09-07T00:00:00Z",
        created_at="2026-09-07T00:00:00Z",
        updated_at="2026-09-07T00:00:00Z",
    )
    data = record.to_dict(redact=True)
    assert "token" not in data["payload"]
    assert "WXYZ-2345" not in data["payload"]["prompt"]
    assert "[redacted]" in data["payload"]["prompt"]
    assert "secret_bearer_error" not in str(data["last_error"])
    assert "[redacted]" in str(data["last_error"])
