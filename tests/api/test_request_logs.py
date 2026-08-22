from __future__ import annotations

import logging

from tests.api.helpers import create_bot, wait_run


def test_thread_send_log_has_request_id_and_redacts_token(
    client, auth_header, host_token, caplog
) -> None:
    caplog.set_level(logging.INFO, logger="artek_buddy")
    bot_id = create_bot(client, auth_header, "ObserveSend")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    request_id = sent.headers.get("x-request-id")
    assert request_id
    snap = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert snap["run"]["status"] == "completed"
    text = caplog.text
    assert host_token not in text
    assert request_id in text
    assert "threads.send" in text
