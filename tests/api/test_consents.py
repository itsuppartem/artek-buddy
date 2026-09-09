from __future__ import annotations

from tests.api.helpers import (
    consent_id_from_thread,
    create_bot,
    wait_pending_auto_jobs,
    wait_run,
    wait_run_status,
)


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


def test_browse_consent_allow_once(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "BrowseAllow")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-consent-browse"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    snap = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input")
    consent_id = consent_id_from_thread(snap)
    allowed = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "allow"},
    )
    assert allowed.status_code == 200
    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["status"] == "completed"
    again = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "allow"},
    )
    assert again.status_code == 400


def test_page_consent_always_grants_future_prompts(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "PageAlways")["id"]
    first = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-consent-page"},
    )
    assert first.status_code == 200
    run_id = first.json()["run_id"]
    snap = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input")
    consent_id = consent_id_from_thread(snap)
    always = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "always"},
    )
    assert always.status_code == 200
    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["status"] == "completed"
    again = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "always"},
    )
    assert again.status_code == 400

    second = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-consent-page"},
    )
    assert second.status_code == 200
    second_run = second.json()["run_id"]
    second_finished = wait_run(client, auth_header, bot_id, second_run)
    assert second_finished["run"]["status"] == "completed"


def test_consent_result_upload(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "ConsentResult")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-consent-auto-read"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    snap = wait_pending_auto_jobs(client, auth_header, bot_id)
    consent_id = snap["pending_auto_consent_id"]
    assert consent_id

    bad = client.post(
        f"/v1/consents/{consent_id}/result",
        headers=auth_header,
        json={"content_base64": "!!!not-valid-base64!!!"},
    )
    assert bad.status_code == 400
    assert "invalid content_base64" in bad.json()["detail"]

    uploaded = client.post(
        f"/v1/consents/{consent_id}/result",
        headers=auth_header,
        json={"ok": True, "text": "owner notes content"},
    )
    assert uploaded.status_code == 200
    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["status"] == "completed"

    duplicate = client.post(
        f"/v1/consents/{consent_id}/result",
        headers=auth_header,
        json={"ok": True, "text": "repeat"},
    )
    assert duplicate.status_code == 409


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
    result = client.post(
        "/v1/consents/cns_missing/result",
        headers=auth_header,
        json={"ok": True},
    )
    assert result.status_code == 404
