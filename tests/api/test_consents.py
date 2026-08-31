from __future__ import annotations

from tests.api.helpers import consent_id_from_thread, create_bot, wait_run, wait_run_status


def test_browse_consent_deny(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "BrowseDeny")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-consent-browse"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    snap = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input")
    consent_id = consent_id_from_thread(snap)
    denied = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "deny"},
    )
    assert denied.status_code == 200
    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["status"] == "failed"
    again = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "deny"},
    )
    assert again.status_code == 400


def test_missing_consent_is_404(client, auth_header) -> None:
    missing = client.get("/v1/consents/cns_missing", headers=auth_header)
    assert missing.status_code == 404
    acknowledged = client.post("/v1/consents/cns_missing/ack", headers=auth_header)
    assert acknowledged.status_code == 404
    answered = client.post(
        "/v1/consents/cns_missing",
        headers=auth_header,
        json={"decision": "deny"},
    )
    assert answered.status_code == 404
