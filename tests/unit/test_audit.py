from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from artek_buddy.audit import (
    GENESIS_HASH,
    AuditRecord,
    canonical_payload_json,
    compute_audit_hash,
    verify_audit_chain,
)


def test_canonical_payload_json_sorts_keys_and_sanitizes_secrets() -> None:
    payload = {
        "b": "value_b",
        "a": "value_a",
        "token": "secret_token_12345",
        "password": "super_secret_password",
        "text": "Call with Bearer test_bearer_abc and code ABCD-EFGH",
    }
    canonical = canonical_payload_json(payload)
    parsed = json.loads(canonical)

    # Forbidden secret keys omitted entirely
    assert "token" not in parsed
    assert "password" not in parsed

    # Sensitive values in strings redacted
    assert "test_bearer_abc" not in parsed["text"]
    assert "ABCD-EFGH" not in parsed["text"]
    assert "[redacted]" in parsed["text"]

    # Keys sorted in serialized output
    assert canonical.index('"a"') < canonical.index('"b"')


def test_compute_audit_hash_deterministic_vectors() -> None:
    # Deterministic vector
    h1 = compute_audit_hash(
        seq=1,
        event_type="member.create",
        actor="system",
        resource="mem_owner",
        payload_json='{"id":"mem_owner","role":"owner"}',
        prev_hash=GENESIS_HASH,
    )
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)

    # Identical inputs yield identical hashes
    h2 = compute_audit_hash(
        seq=1,
        event_type="member.create",
        actor="system",
        resource="mem_owner",
        payload_json='{"id":"mem_owner","role":"owner"}',
        prev_hash=GENESIS_HASH,
    )
    assert h1 == h2

    # Any single field change changes the hash
    h_diff = compute_audit_hash(
        seq=1,
        event_type="member.create",
        actor="system",
        resource="mem_owner",
        payload_json='{"id":"mem_owner","role":"member"}',
        prev_hash=GENESIS_HASH,
    )
    assert h1 != h_diff


def test_verify_audit_chain_valid_chain() -> None:
    records: list[AuditRecord] = []
    prev_h = GENESIS_HASH

    for i in range(1, 4):
        payload = {"step": i, "data": f"action_{i}"}
        payload_json = canonical_payload_json(payload)
        h = compute_audit_hash(
            seq=i,
            event_type="test.event",
            actor="owner",
            resource=f"res_{i}",
            payload_json=payload_json,
            prev_hash=prev_h,
        )
        records.append(
            AuditRecord(
                seq=i,
                id=f"aud_{i}",
                event_type="test.event",
                actor="owner",
                resource=f"res_{i}",
                payload=payload,
                prev_hash=prev_h,
                hash=h,
                created_at="2026-09-07T00:00:00Z",
            )
        )
        prev_h = h

    res = verify_audit_chain(records)
    assert res.ok is True
    assert res.total_events == 3
    assert res.head_hash == records[-1].hash
    assert res.failed_seq is None


def test_verify_audit_chain_detects_tampered_payload_byte() -> None:
    records: list[AuditRecord] = []
    prev_h = GENESIS_HASH

    for i in range(1, 4):
        payload = {"step": i, "data": f"action_{i}"}
        payload_json = canonical_payload_json(payload)
        h = compute_audit_hash(
            seq=i,
            event_type="test.event",
            actor="owner",
            resource=f"res_{i}",
            payload_json=payload_json,
            prev_hash=prev_h,
        )
        records.append(
            AuditRecord(
                seq=i,
                id=f"aud_{i}",
                event_type="test.event",
                actor="owner",
                resource=f"res_{i}",
                payload=payload,
                prev_hash=prev_h,
                hash=h,
                created_at="2026-09-07T00:00:00Z",
            )
        )
        prev_h = h

    # Tamper with record 2 payload (even by a single character)
    records[1].payload["data"] = "tampered_action_2"

    res = verify_audit_chain(records)
    assert res.ok is False
    assert res.failed_seq == 2
    assert "Hash mismatch at seq 2" in str(res.reason)


def test_verify_audit_chain_detects_broken_chain_prev_hash() -> None:
    records: list[AuditRecord] = []
    prev_h = GENESIS_HASH

    for i in range(1, 3):
        payload = {"step": i}
        payload_json = canonical_payload_json(payload)
        h = compute_audit_hash(
            seq=i,
            event_type="test.event",
            actor="owner",
            resource=f"res_{i}",
            payload_json=payload_json,
            prev_hash=prev_h,
        )
        records.append(
            AuditRecord(
                seq=i,
                id=f"aud_{i}",
                event_type="test.event",
                actor="owner",
                resource=f"res_{i}",
                payload=payload,
                prev_hash=prev_h,
                hash=h,
                created_at="2026-09-07T00:00:00Z",
            )
        )
        prev_h = h

    # Tamper with prev_hash of record 2
    records[1].prev_hash = "f" * 64

    res = verify_audit_chain(records)
    assert res.ok is False
    assert res.failed_seq == 2
    assert "Broken chain at seq 2" in str(res.reason)


def test_verify_audit_chain_detects_genesis_hash_mismatch() -> None:
    payload = {"step": 1}
    payload_json = canonical_payload_json(payload)
    h = compute_audit_hash(1, "test", "owner", "res", payload_json, "bad_genesis")
    record = AuditRecord(
        seq=1,
        id="aud_1",
        event_type="test",
        actor="owner",
        resource="res",
        payload=payload,
        prev_hash="bad_genesis",
        hash=h,
        created_at="2026-09-07T00:00:00Z",
    )
    res = verify_audit_chain([record])
    assert res.ok is False
    assert res.failed_seq == 1
    assert "Genesis prev_hash mismatch" in str(res.reason)
