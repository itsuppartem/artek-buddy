from __future__ import annotations

import json
from pathlib import Path

from tests.api.helpers import create_bot, message_texts

from artek_buddy.bot_credentials import (
    PASTED_CREDENTIAL_DETAIL,
    BotCredentialStore,
    last_four,
)
from artek_buddy.computer.service import wipe_computer_home

GITHUB_FIXTURE = "ghp_" + ("A" * 36)
PYPI_FIXTURE = "pypi-AgEIcHlwaS5vcmc" + ("B" * 16)


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
    assert saved_g.status_code == 200, saved_g.text
    assert saved_p.status_code == 200, saved_p.text
    assert GITHUB_FIXTURE not in saved_g.text
    assert PYPI_FIXTURE not in saved_p.text
    assert saved_g.json()["last_four"] == last_four(GITHUB_FIXTURE)
    assert saved_g.json()["scope"] == "this_bot"

    listed_a = client.get(f"/v1/bots/{alpha}/credentials", headers=auth_header)
    listed_b = client.get(f"/v1/bots/{bravo}/credentials", headers=auth_header)
    assert listed_a.status_code == 200
    assert listed_b.status_code == 200
    assert GITHUB_FIXTURE not in listed_a.text
    assert PYPI_FIXTURE not in listed_a.text
    assert {row["provider"] for row in listed_a.json()["credentials"]} == {"github", "pypi"}
    assert listed_b.json()["credentials"] == []

    vault = BotCredentialStore(client.app.state.settings.agent_data_dir)
    assert vault.read(alpha, "github") == GITHUB_FIXTURE
    assert vault.read(alpha, "pypi") == PYPI_FIXTURE
    assert vault.read(bravo, "github") is None
    assert vault.tool_env(bravo) == {}
    env = vault.tool_env(alpha)
    assert env["GH_TOKEN"] == GITHUB_FIXTURE
    assert env["TWINE_PASSWORD"] == PYPI_FIXTURE
    assert "https://" not in " ".join(env.values())


def test_fresh_app_over_same_data_keeps_tokens(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CredFresh")["id"]
    assert _put(client, auth_header, bot_id, "github", GITHUB_FIXTURE).status_code == 200
    assert _put(client, auth_header, bot_id, "pypi", PYPI_FIXTURE).status_code == 200
    data = Path(client.app.state.settings.agent_data_dir)
    revived = BotCredentialStore(data)
    assert revived.read(bot_id, "github") == GITHUB_FIXTURE
    assert revived.read(bot_id, "pypi") == PYPI_FIXTURE
    assert revived.tool_env(bot_id)["GH_TOKEN"] == GITHUB_FIXTURE
    assert revived.tool_env(bot_id)["UV_PUBLISH_TOKEN"] == PYPI_FIXTURE


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
    vault = BotCredentialStore(client.app.state.settings.agent_data_dir)
    assert vault.read(bot_id, "github") == GITHUB_FIXTURE

    switched = client.patch(
        f"/v1/bots/{bot_id}",
        headers=auth_header,
        json={"computer_mode": "team"},
    )
    assert switched.status_code == 200, switched.text
    again = client.get(f"/v1/bots/{bot_id}/credentials", headers=auth_header)
    assert again.json()["credentials"][0]["last_four"] == last_four(GITHUB_FIXTURE)
    assert vault.read(bot_id, "github") == GITHUB_FIXTURE


def test_replace_delete_and_forget_drop_old_secret(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CredForget")["id"]
    assert _put(client, auth_header, bot_id, "github", GITHUB_FIXTURE).status_code == 200
    replacement = "ghp_" + ("D" * 36)
    swapped = _put(client, auth_header, bot_id, "github", replacement)
    assert swapped.status_code == 200
    vault = BotCredentialStore(client.app.state.settings.agent_data_dir)
    assert vault.read(bot_id, "github") == replacement
    assert vault.read(bot_id, "github") != GITHUB_FIXTURE
    forgotten = client.delete(f"/v1/bots/{bot_id}/credentials/github", headers=auth_header)
    assert forgotten.status_code == 200
    assert vault.read(bot_id, "github") is None
    assert _put(client, auth_header, bot_id, "pypi", PYPI_FIXTURE).status_code == 200
    removed = client.delete(f"/v1/bots/{bot_id}", headers=auth_header)
    assert removed.status_code == 200
    assert vault.read(bot_id, "pypi") is None


def test_chat_paste_is_rejected_before_persist(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CredPaste")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": f"here {GITHUB_FIXTURE}"},
    )
    assert sent.status_code == 400
    assert sent.json()["detail"] == PASTED_CREDENTIAL_DETAIL
    assert GITHUB_FIXTURE not in sent.text
    snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert snap.status_code == 200
    blob = _dump(snap.json())
    assert GITHUB_FIXTURE not in blob
    assert GITHUB_FIXTURE not in " ".join(message_texts(snap.json()))
    listed = client.get(f"/v1/threads/{bot_id}/messages", headers=auth_header)
    assert GITHUB_FIXTURE not in listed.text


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
