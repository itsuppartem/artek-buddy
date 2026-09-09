from __future__ import annotations

from tests.api.helpers import consent_id_from_thread, create_bot, wait_run, wait_run_status

from artek_buddy.runtime.scripted_scenarios import (
    E2E_SCENARIO_RESEARCH_BODY,
    E2E_SCENARIO_RESEARCH_FILE,
)


def _bot_file_blocks(snap: dict) -> list[dict]:
    return [
        block
        for msg in snap.get("messages") or []
        if msg.get("role") == "bot"
        for block in msg.get("blocks") or []
        if block.get("kind") == "file"
    ]


def test_scenario_research_allow_posts_brief_with_required_sections(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "ScenarioResearchAllow")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-scenario-research"},
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
    assert allowed.status_code == 200, allowed.text
    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["status"] == "completed"
    files = _bot_file_blocks(finished)
    assert len(files) == 1
    assert files[0]["name"] == E2E_SCENARIO_RESEARCH_FILE
    art_id = files[0]["artifact_id"]
    downloaded = client.get(f"/v1/artifacts/{art_id}", headers=auth_header)
    assert downloaded.status_code == 200
    body = downloaded.content.decode("utf-8")
    assert body == E2E_SCENARIO_RESEARCH_BODY
    assert "## Answer" in body
    assert "## Sources" in body
    assert "## Unknowns" in body
    assert "https://docs.python.org/3/whatsnew/3.13.html" in body


def test_scenario_research_deny_does_not_post_a_file(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "ScenarioResearchDeny")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-scenario-research"},
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
    assert denied.status_code == 200, denied.text
    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["status"] == "failed"
    assert _bot_file_blocks(finished) == []
