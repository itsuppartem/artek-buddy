from __future__ import annotations

from tests.api.helpers import create_bot, wait_run


def test_workspace_dispatch_routes_without_creating_a_lead_chat(client, auth_header) -> None:
    create_bot(client, auth_header, "WorkspaceDispatchMail")
    release = create_bot(client, auth_header, "WorkspaceDispatchRelease")
    before = client.get("/v1/bots", headers=auth_header)
    assert before.status_code == 200
    before_ids = {item["id"] for item in before.json()["bots"]}

    sent = client.post(
        "/v1/workspace/dispatch",
        headers=auth_header,
        json={"text": "WorkspaceDispatchRelease: verify the package"},
    )

    assert sent.status_code == 200, sent.text
    assert sent.json()["bot_id"] == release["id"]
    wait_run(client, auth_header, release["id"], sent.json()["run_id"])
    bots = client.get("/v1/bots", headers=auth_header)
    assert bots.status_code == 200
    assert {item["id"] for item in bots.json()["bots"]} == before_ids
