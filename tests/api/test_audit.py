from __future__ import annotations

import json

import pytest

from artek_buddy.__main__ import audit_export, audit_verify


def test_audit_records_on_device_and_member_actions(client, host_token) -> None:
    store = client.app.state.store

    # 1. Verification initially passes
    report = store.verify_audit()
    assert report.ok is True

    # 2. Pair a new device
    code = client.post(
        "/v1/devices/pairing",
        headers={"Authorization": f"Bearer {host_token}"},
    ).json()["code"]

    dev_res = client.post(
        "/v1/devices",
        json={"name": "AuditDevice", "platform": "linux", "pairing_code": code},
    )
    assert dev_res.status_code == 200
    dev_data = dev_res.json()
    dev_id = dev_data["id"]
    token = dev_data["token"]

    # 3. Check audit chain contains device.create event without raw token
    chain = store.get_audit_chain()
    dev_create_events = [
        e for e in chain if e.event_type == "device.create" and e.resource == dev_id
    ]
    assert len(dev_create_events) == 1
    event = dev_create_events[0]
    assert event.payload["id"] == dev_id
    assert "token" not in event.payload
    assert "token_hash" not in event.payload
    assert token not in json.dumps(event.payload)

    # 4. Revoke the device
    del_res = client.delete(
        f"/v1/devices/{dev_id}",
        headers={"Authorization": f"Bearer {host_token}"},
    )
    assert del_res.status_code == 200

    # 5. Check audit chain contains device.revoke
    chain_after_revoke = store.get_audit_chain()
    dev_revoke_events = [
        e for e in chain_after_revoke if e.event_type == "device.revoke" and e.resource == dev_id
    ]
    assert len(dev_revoke_events) == 1

    # 6. Entire chain remains verified
    assert store.verify_audit().ok is True


def test_audit_detects_database_tampering(client) -> None:
    store = client.app.state.store
    chain = store.get_audit_chain()
    if not chain:
        store.ensure_owner_member()
        chain = store.get_audit_chain()
    assert len(chain) > 0

    target = chain[0]

    # Tamper with the payload directly in the database
    with store._conn() as conn:
        conn.execute(
            "UPDATE audit SET payload = %s::jsonb WHERE seq = %s",
            (json.dumps({"tampered": True}), target.seq),
        )
        conn.commit()

    try:
        # Verification MUST fail now
        res = store.verify_audit()
        assert res.ok is False
        assert res.failed_seq == target.seq
        assert "Hash mismatch" in str(res.reason)
    finally:
        # Restore original payload so subsequent tests are not affected
        with store._conn() as conn:
            conn.execute(
                "UPDATE audit SET payload = %s::jsonb WHERE seq = %s",
                (json.dumps(target.payload), target.seq),
            )
            conn.commit()

    # Once restored, verification passes again
    assert store.verify_audit().ok is True


def test_audit_verify_and_export_cli_commands(client, capsys) -> None:
    # CLI audit_verify returns 0 on uncorrupted DB
    code = audit_verify()
    assert code == 0
    out = capsys.readouterr().out
    assert "Audit chain valid:" in out

    # CLI audit_export prints valid JSON array
    code_exp = audit_export()
    assert code_exp == 0
    export_out = capsys.readouterr().out
    exported = json.loads(export_out)
    assert isinstance(exported, list)
    if exported:
        assert "seq" in exported[0]
        assert "hash" in exported[0]


def test_get_audit_api_endpoint(client, auth_header) -> None:
    # 1. Owner can access GET /v1/audit
    res = client.get("/v1/audit", headers=auth_header)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "total_events" in data
    assert "head_hash" in data
    assert isinstance(data["events"], list)
