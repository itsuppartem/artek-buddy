from __future__ import annotations

import json
import time
from pathlib import Path

from tests.api.helpers import (
    consent_id_from_thread,
    create_bot,
    message_texts,
    wait_run,
    wait_thread_has,
)

from artek_buddy.bot_credentials import (
    PASTED_CREDENTIAL_DETAIL,
    UNNAMED_CREDENTIAL_DETAIL,
    CredentialStoreUnavailable,
    last_four,
)
from artek_buddy.computer.service import wipe_computer_home

GITHUB_FIXTURE = "ghp_" + ("A" * 36)
PYPI_FIXTURE = "pypi-AgEIcHlwaS5vcmc" + ("B" * 16)
NAMED_FIXTURE = "reg_" + ("Z" * 24)


def _dump(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _put(client, auth_header, bot_id: str, provider: str, secret: str):
    return client.put(
        f"/v1/bots/{bot_id}/credentials/{provider}",
        headers=auth_header,
        json={"secret": secret},
    )


def test_credentials_survive_new_store_and_stay_isolated(client, auth_header) -> None:
    alpha = create_bot(client, auth_header, "CredAlpha")["id"]
    bravo = create_bot(client, auth_header, "CredBravo")["id"]
    saved_g = _put(client, auth_header, alpha, "github", GITHUB_FIXTURE)
    saved_p = _put(client, auth_header, alpha, "pypi", PYPI_FIXTURE)
    saved_n = _put(client, auth_header, alpha, "registry-token", NAMED_FIXTURE)
    assert saved_g.status_code == 200, saved_g.text
    assert saved_p.status_code == 200, saved_p.text
    assert saved_n.status_code == 200, saved_n.text
    assert GITHUB_FIXTURE not in saved_g.text
    assert PYPI_FIXTURE not in saved_p.text
    assert NAMED_FIXTURE not in saved_n.text
    assert saved_g.json()["last_four"] == last_four(GITHUB_FIXTURE)
    assert saved_n.json()["last_four"] == last_four(NAMED_FIXTURE)
    assert saved_g.json()["env_name"] == "GH_TOKEN"
    assert saved_n.json()["env_name"] == "REGISTRY_TOKEN"
    assert saved_g.json()["scope"] == "this_bot"

    listed_a = client.get(f"/v1/bots/{alpha}/credentials", headers=auth_header)
    listed_b = client.get(f"/v1/bots/{bravo}/credentials", headers=auth_header)
    assert listed_a.status_code == 200
    assert listed_b.status_code == 200
    assert GITHUB_FIXTURE not in listed_a.text
    assert PYPI_FIXTURE not in listed_a.text
    assert NAMED_FIXTURE not in listed_a.text
    assert {row["provider"] for row in listed_a.json()["credentials"]} == {
        "github",
        "pypi",
        "registry-token",
    }
    assert listed_b.json()["credentials"] == []

    assert {row.provider for row in client.app.state.credential_store.list_for_bot(alpha)} == {
        "github",
        "pypi",
        "registry-token",
    }
    assert client.app.state.credential_store.list_for_bot(bravo) == []
    assert not (Path(client.app.state.settings.agent_data_dir) / "credentials").exists()


def test_settings_storage_never_writes_under_app_data(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CredFresh")["id"]
    assert _put(client, auth_header, bot_id, "github", GITHUB_FIXTURE).status_code == 200
    assert _put(client, auth_header, bot_id, "pypi", PYPI_FIXTURE).status_code == 200
    data = Path(client.app.state.settings.agent_data_dir)
    assert not (data / "credentials").exists()
    listed = client.get(f"/v1/bots/{bot_id}/credentials", headers=auth_header)
    assert listed.status_code == 200
    assert {row["provider"] for row in listed.json()["credentials"]} == {"github", "pypi"}


def test_reset_and_mode_switch_keep_credentials(client, auth_header) -> None:
    bot = create_bot(client, auth_header, "CredReset", computer_mode="dedicated")
    bot_id = bot["id"]
    assert _put(client, auth_header, bot_id, "github", GITHUB_FIXTURE).status_code == 200
    history = client.app.state.store
    record = history.get_computer_for_bot(history.get_bot(bot_id))
    home = Path(client.app.state.settings.agent_data_dir) / "homes" / record.home_key
    home.mkdir(parents=True, exist_ok=True)
    (home / "marker.txt").write_text("wipe-me", encoding="utf-8")
    reset = client.post(f"/v1/computer/{bot_id}/reset", headers=auth_header)
    assert reset.status_code == 200, reset.text
    wipe_computer_home(Path(client.app.state.settings.agent_data_dir), record.home_key)
    listed = client.get(f"/v1/bots/{bot_id}/credentials", headers=auth_header)
    assert listed.status_code == 200
    assert listed.json()["credentials"][0]["last_four"] == last_four(GITHUB_FIXTURE)
    after_reset = client.app.state.credential_store.execute(
        bot_id,
        record.home_key,
        "check GH_TOKEN",
    )
    assert after_reset.ok is True
    assert after_reset.stdout == "credential available\n"

    switched = client.patch(
        f"/v1/bots/{bot_id}",
        headers=auth_header,
        json={"computer_mode": "team"},
    )
    assert switched.status_code == 200, switched.text
    again = client.get(f"/v1/bots/{bot_id}/credentials", headers=auth_header)
    assert again.json()["credentials"][0]["last_four"] == last_four(GITHUB_FIXTURE)
    team_record = history.get_computer_for_bot(history.get_bot(bot_id))
    after_switch = client.app.state.credential_store.execute(
        bot_id,
        team_record.home_key,
        "check GH_TOKEN",
    )
    assert after_switch.stdout == "credential available\n"


def test_replace_delete_and_forget_drop_old_secret(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CredForget")["id"]
    assert _put(client, auth_header, bot_id, "github", GITHUB_FIXTURE).status_code == 200
    replacement = "ghp_" + ("D" * 36)
    swapped = _put(client, auth_header, bot_id, "github", replacement)
    assert swapped.status_code == 200
    listed = client.get(f"/v1/bots/{bot_id}/credentials", headers=auth_header)
    assert listed.json()["credentials"][0]["last_four"] == "DDDD"
    forgotten = client.delete(f"/v1/bots/{bot_id}/credentials/github", headers=auth_header)
    assert forgotten.status_code == 200
    assert (
        client.get(f"/v1/bots/{bot_id}/credentials", headers=auth_header).json()["credentials"]
        == []
    )
    assert _put(client, auth_header, bot_id, "pypi", PYPI_FIXTURE).status_code == 200
    removed = client.delete(f"/v1/bots/{bot_id}", headers=auth_header)
    assert removed.status_code == 200
    assert client.app.state.credential_store.list_for_bot(bot_id) == []


def test_chat_named_token_is_stored_not_persisted(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CredPaste")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": f"use REGISTRY_TOKEN={NAMED_FIXTURE} to publish"},
    )
    assert sent.status_code == 200, sent.text
    blob = _dump(sent.json())
    assert NAMED_FIXTURE not in blob
    snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert snap.status_code == 200
    assert NAMED_FIXTURE not in _dump(snap.json())
    assert NAMED_FIXTURE not in " ".join(message_texts(snap.json()))
    user_text = " ".join(message_texts(snap.json()))
    assert "use" in user_text
    assert last_four(NAMED_FIXTURE) in user_text
    listed = client.get(f"/v1/threads/{bot_id}/messages", headers=auth_header)
    assert NAMED_FIXTURE not in listed.text
    creds = client.get(f"/v1/bots/{bot_id}/credentials", headers=auth_header)
    assert creds.status_code == 200
    assert NAMED_FIXTURE not in creds.text
    names = {row["provider"] for row in creds.json()["credentials"]}
    assert "registry-token" in names
    assert client.app.state.credential_store.list_for_bot(bot_id)[0].last_four == "ZZZZ"


def test_scripted_credential_turn_delegates_and_keeps_fixture_out_of_history(
    client,
    auth_header,
    caplog,
) -> None:
    bot_id = create_bot(client, auth_header, "CredScripted")["id"]
    pasted = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": f"REGISTRY_TOKEN={NAMED_FIXTURE}"},
    )
    assert pasted.status_code == 200
    wait_run(client, auth_header, bot_id, pasted.json()["run_id"])

    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-credential-command"},
    )
    assert sent.status_code == 200
    lead = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert lead["run"]["status"] == "completed"

    deadline = time.time() + 10
    consent_id = None
    while time.time() < deadline:
        snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
        assert snap.status_code == 200
        try:
            consent_id = consent_id_from_thread(snap.json())
            break
        except AssertionError:
            time.sleep(0.1)
    assert consent_id is not None
    allowed = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "once"},
    )
    assert allowed.status_code == 200, allowed.text

    deadline = time.time() + 10
    worker = None
    while time.time() < deadline:
        listed = client.get(f"/v1/bots/{bot_id}/subagents", headers=auth_header)
        assert listed.status_code == 200
        workers = [
            item for item in listed.json()["subagents"] if item.get("name") == "CredentialWorker"
        ]
        if workers and workers[0].get("status") == "completed":
            worker = workers[0]
            break
        time.sleep(0.1)
    assert worker is not None
    assert "Credential-scoped command finished." in str(worker.get("result") or "")

    final = wait_thread_has(
        client,
        auth_header,
        bot_id,
        "The background job is done.",
    )
    assert message_texts(final).count("The background job is done.") == 1
    thread = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    messages = client.get(f"/v1/threads/{bot_id}/messages", headers=auth_header)
    packed = thread.text + messages.text + json.dumps(worker)
    assert NAMED_FIXTURE not in packed
    assert "env.sh" not in packed
    assert "ZZZZ" in packed
    resumed = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "continue"},
    )
    assert resumed.status_code == 200
    wait_run(client, auth_header, bot_id, resumed.json()["run_id"])
    assert NAMED_FIXTURE not in str(client.app.state.runtime.last_prompt or "")
    assert NAMED_FIXTURE not in caplog.text


def test_unlabeled_chat_blob_is_refused(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CredBlob")["id"]
    blob = "AbCdEfGhIjKlMnOpQrStUvWxYz012345"
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": blob},
    )
    assert sent.status_code == 400
    assert sent.json()["detail"] == UNNAMED_CREDENTIAL_DETAIL
    assert blob not in sent.text
    snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert blob not in _dump(snap.json())
    creds = client.get(f"/v1/bots/{bot_id}/credentials", headers=auth_header)
    assert creds.json()["credentials"] == []


def test_memory_and_answer_reject_pasted_tokens(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CredMem")["id"]
    memory = client.post(
        "/v1/memory",
        headers=auth_header,
        json={"scope": "bot", "bot_id": bot_id, "content": PYPI_FIXTURE},
    )
    assert memory.status_code == 400
    assert memory.json()["detail"] == PASTED_CREDENTIAL_DETAIL
    docs = client.get("/v1/memory", headers=auth_header, params={"bot_id": bot_id})
    assert PYPI_FIXTURE not in docs.text
    answer = client.post(
        f"/v1/threads/{bot_id}/answer",
        headers=auth_header,
        json={
            "run_id": "run_missing",
            "message_id": "msg_missing",
            "answer": GITHUB_FIXTURE,
        },
    )
    assert answer.status_code == 400
    assert GITHUB_FIXTURE not in answer.text


def test_settings_and_chat_fail_closed_when_broker_is_unavailable(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CredUnavailable")["id"]

    class Unavailable:
        def put(self, *_args, **_kwargs):
            raise CredentialStoreUnavailable("fixture must not escape")

        def forget_bot(self, *_args, **_kwargs):
            raise CredentialStoreUnavailable("fixture must not escape")

    original = client.app.state.credential_store
    client.app.state.credential_store = Unavailable()
    client.app.state.runtime.credential_store = client.app.state.credential_store
    try:
        saved = _put(client, auth_header, bot_id, "github", GITHUB_FIXTURE)
        assert saved.status_code == 503
        assert GITHUB_FIXTURE not in saved.text
        sent = client.post(
            f"/v1/threads/{bot_id}/messages",
            headers=auth_header,
            json={"text": f"REGISTRY_TOKEN={NAMED_FIXTURE}"},
        )
        assert sent.status_code == 503
        assert NAMED_FIXTURE not in sent.text
        removed = client.delete(f"/v1/bots/{bot_id}", headers=auth_header)
        assert removed.status_code == 503
        assert client.get(f"/v1/bots/{bot_id}", headers=auth_header).status_code == 200
    finally:
        client.app.state.credential_store = original
        client.app.state.runtime.credential_store = original
