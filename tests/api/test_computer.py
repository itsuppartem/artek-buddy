from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from tests.api.helpers import consent_id_from_thread, create_bot, wait_run_status


def test_computer_boot_stop_on_fake(client, auth_header) -> None:
    bot = client.post(
        "/v1/bots",
        headers=auth_header,
        json={"name": "Desk", "computer_mode": "dedicated"},
    )
    bot_id = bot.json()["id"]
    status = client.get(f"/v1/computer/{bot_id}", headers=auth_header)
    assert status.status_code == 200
    assert status.json()["kind"] in {"fake", "docker", "desktop"}

    booted = client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header)
    assert booted.status_code == 200
    assert booted.json()["state"] == "running"

    screen = client.get(f"/v1/computer/{bot_id}/screen", headers=auth_header)
    assert screen.status_code == 200
    assert screen.json()["url"] is None

    stopped = client.post(f"/v1/computer/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "suspended"


def test_computer_restart_and_reset(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "RestartBox", computer_mode="dedicated")["id"]
    booted = client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header)
    assert booted.status_code == 200
    restarted = client.post(f"/v1/computer/{bot_id}/restart", headers=auth_header)
    assert restarted.status_code == 200
    assert restarted.json()["state"] == "running"
    reset = client.post(f"/v1/computer/{bot_id}/reset", headers=auth_header)
    assert reset.status_code == 200
    assert reset.json()["state"] == "stopped"


def test_team_status_names_the_bot_that_booted(client, auth_header) -> None:
    alpha = client.post(
        "/v1/bots",
        headers=auth_header,
        json={"name": "AlphaHold", "computer_mode": "team"},
    )
    bravo = client.post(
        "/v1/bots",
        headers=auth_header,
        json={"name": "BravoWait", "computer_mode": "team"},
    )
    assert alpha.status_code == 200
    assert bravo.status_code == 200
    alpha_id = alpha.json()["id"]
    bravo_id = bravo.json()["id"]

    booted = client.post(f"/v1/computer/{alpha_id}/boot", headers=auth_header)
    assert booted.status_code == 200
    taken = client.post(f"/v1/computer/{alpha_id}/takeover", headers=auth_header)
    assert taken.status_code == 200

    waiting = client.get(f"/v1/computer/{bravo_id}", headers=auth_header)
    assert waiting.status_code == 200
    body = waiting.json()
    assert body["state"] == "running"
    assert body["busy_bot_name"] == "AlphaHold"
    assert body["control_holder"] != "user"

    blocked = client.post(f"/v1/computer/{bravo_id}/reset", headers=auth_header)
    assert blocked.status_code == 409


def test_computer_files_and_path_jail(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "FilesBox", computer_mode="dedicated")["id"]
    booted = client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header)
    assert booted.status_code == 200
    listed = client.get(f"/v1/computer/{bot_id}/files", headers=auth_header)
    assert listed.status_code == 200
    assert "entries" in listed.json()
    escaped = client.get(
        f"/v1/computer/{bot_id}/files", headers=auth_header, params={"path": "../secret"}
    )
    assert escaped.status_code == 400
    missing = client.get(
        f"/v1/computer/{bot_id}/files/read",
        headers=auth_header,
        params={"path": "no-such-file.txt"},
    )
    assert missing.status_code == 400


def test_computer_file_download(client, auth_header, tmp_path) -> None:
    bot_id = create_bot(client, auth_header, "RawBox", computer_mode="dedicated")["id"]
    booted = client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header)
    assert booted.status_code == 200
    home = tmp_path / "data" / "homes" / bot_id
    home.mkdir(parents=True, exist_ok=True)
    (home / "hello.txt").write_bytes(b"from the box\n")

    listed = client.get(f"/v1/computer/{bot_id}/files", headers=auth_header)
    assert listed.status_code == 200
    names = [entry["name"] for entry in listed.json()["entries"]]
    assert "hello.txt" in names

    raw = client.get(
        f"/v1/computer/{bot_id}/files/raw",
        headers=auth_header,
        params={"path": "hello.txt"},
    )
    assert raw.status_code == 200
    assert raw.content == b"from the box\n"
    disposition = raw.headers.get("content-disposition") or ""
    assert "hello.txt" in disposition

    missing = client.get(
        f"/v1/computer/{bot_id}/files/raw",
        headers=auth_header,
        params={"path": "no-such-file.txt"},
    )
    assert missing.status_code == 400
    escaped = client.get(
        f"/v1/computer/{bot_id}/files/raw",
        headers=auth_header,
        params={"path": "../secret"},
    )
    assert escaped.status_code == 400
    no_path = client.get(f"/v1/computer/{bot_id}/files/raw", headers=auth_header)
    assert no_path.status_code == 422


def test_computer_input_needs_takeover(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "InputBox", computer_mode="dedicated")["id"]
    booted = client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header)
    assert booted.status_code == 200
    denied = client.post(
        f"/v1/computer/{bot_id}/input",
        headers=auth_header,
        json={"kind": "key", "payload": {"text": "a"}},
    )
    assert denied.status_code == 400
    taken = client.post(f"/v1/computer/{bot_id}/takeover", headers=auth_header)
    assert taken.status_code == 200
    typed = client.post(
        f"/v1/computer/{bot_id}/input",
        headers=auth_header,
        json={"kind": "key", "payload": {"text": "a"}},
    )
    assert typed.status_code == 200
    beat = client.post(f"/v1/computer/{bot_id}/heartbeat", headers=auth_header)
    assert beat.status_code == 200
    released = client.post(f"/v1/computer/{bot_id}/release", headers=auth_header)
    assert released.status_code == 200
    assert released.json()["ok"] is True
    after = client.get(f"/v1/computer/{bot_id}", headers=auth_header)
    assert after.status_code == 200
    assert after.json()["control_holder"] != "user"


def test_default_observe_has_no_image_when_title_is_useful(client, auth_header) -> None:
    from artek_buddy.main import app

    bot_id = create_bot(client, auth_header, "ObsSlim", computer_mode="dedicated")["id"]
    booted = client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header)
    assert booted.status_code == 200
    bot = app.state.store.get_bot(bot_id)
    result = app.state.computers.observe(bot)
    assert result["ok"] is True
    assert result["title"] == "Inbox - Gmail"
    assert result["image_reason"] == "none"
    assert "image_png_base64" not in result
    assert "content" not in result


def test_generic_title_attaches_typed_image_not_json_field(client, auth_header) -> None:
    from artek_buddy.main import app

    bot_id = create_bot(client, auth_header, "ObsGeneric", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    bot = app.state.store.get_bot(bot_id)
    record = app.state.computers.store.get_computer_for_bot(bot)
    app.state.computers.client.boxes[record.provider_ref]["title"] = "Chromium"
    result = app.state.computers.observe(bot)
    assert "image_png_base64" not in result
    assert result["image_reason"] == "generic_title"
    assert result["content"][0]["type"] == "image"
    assert result["content"][0]["mime_type"] == "image/png"
    assert result["content"][0]["data"]


def test_include_image_attaches_even_with_good_title(client, auth_header) -> None:
    from artek_buddy.main import app

    bot_id = create_bot(client, auth_header, "ObsShot", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    bot = app.state.store.get_bot(bot_id)
    result = app.state.computers.observe(bot, include_image=True)
    assert result["image_reason"] == "requested"
    assert "image_png_base64" not in result
    assert result["content"][0]["type"] == "image"


def test_computer_act_batch_can_return_slim_observe(client, auth_header) -> None:
    from artek_buddy.main import app

    bot_id = create_bot(client, auth_header, "ActBatch", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    bot = app.state.store.get_bot(bot_id)
    result = app.state.computers.act(
        bot,
        [
            {"kind": "click", "x": 10, "y": 10},
            {"kind": "wait", "ms": 10},
            {"kind": "click", "x": 20, "y": 20},
        ],
        return_observe=True,
    )
    acts = [call for call in app.state.computers.client.calls if call[0] == "act"]
    assert len(acts[-1][1]) == 3
    assert "observe" in result
    assert "image_png_base64" not in result["observe"]
    assert result["observe"]["title"] == "Inbox - Gmail"


def test_caps_lock_reaches_sandbox_display(client, auth_header) -> None:
    from artek_buddy.main import app

    bot_id = create_bot(client, auth_header, "CapsBox", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    denied = client.post(
        f"/v1/computer/{bot_id}/input",
        headers=auth_header,
        json={"kind": "key", "payload": {"key": "Caps_Lock"}},
    )
    assert denied.status_code == 400
    taken = client.post(f"/v1/computer/{bot_id}/takeover", headers=auth_header)
    assert taken.status_code == 200
    caps = client.post(
        f"/v1/computer/{bot_id}/input",
        headers=auth_header,
        json={"kind": "key", "payload": {"key": "CapsLock"}},
    )
    assert caps.status_code == 200
    typed = client.post(
        f"/v1/computer/{bot_id}/input",
        headers=auth_header,
        json={"kind": "key", "payload": {"text": "abc"}},
    )
    assert typed.status_code == 200
    bot = app.state.store.get_bot(bot_id)
    record = app.state.computers.store.get_computer_for_bot(bot)
    box = app.state.computers.client.boxes[record.provider_ref]
    assert box["typed"][-1] == "ABC"


def test_startup_does_not_respawn_xterm_when_browser_is_up(client, auth_header) -> None:
    from artek_buddy.main import app

    bot_id = create_bot(client, auth_header, "TermBox", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    bot = app.state.store.get_bot(bot_id)
    record = app.state.computers.store.get_computer_for_bot(bot)
    box = app.state.computers.client.boxes[record.provider_ref]
    assert box["xterm_spawns"] == 0
    app.state.computers.launch_app(bot, "terminal")
    assert box["xterm_spawns"] == 1
    app.state.computers.observe(bot)
    app.state.computers.act(bot, [{"kind": "click", "x": 1, "y": 1}])
    assert box["xterm_spawns"] == 1


def test_computer_requires_auth(client) -> None:
    response = client.get("/v1/computer/bot_missing")
    assert response.status_code == 401


def test_open_path_from_stopped_emits_computer_status(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "WakeBox", computer_mode="dedicated")["id"]
    before = client.get(f"/v1/computer/{bot_id}", headers=auth_header)
    assert before.status_code == 200
    assert before.json()["state"] == "stopped"

    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-wake-computer"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    snap = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input")
    consent_id = consent_id_from_thread(snap)
    allowed = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "always"},
    )
    assert allowed.status_code == 200

    deadline = time.time() + 8.0
    types: list[str] = []
    while time.time() < deadline:
        types = [
            event.type.value if hasattr(event.type, "value") else str(event.type)
            for event in client.app.state.hub.replay(bot_id)
        ]
        if "computer.status" in types:
            break
        time.sleep(0.1)
    else:
        raise AssertionError(f"no computer.status in {types}")

    after = client.get(f"/v1/computer/{bot_id}", headers=auth_header)
    assert after.status_code == 200
    assert after.json()["state"] == "running"


@pytest.mark.asyncio
async def test_computer_input_does_not_block_the_event_loop(
    client, auth_header, monkeypatch
) -> None:
    from artek_buddy.main import app

    bot_id = create_bot(client, auth_header, "LoopBox", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    taken = client.post(f"/v1/computer/{bot_id}/takeover", headers=auth_header)
    assert taken.status_code == 200

    real = app.state.computers.send_input

    def slow_send_input(bot, kind, payload):
        time.sleep(0.45)
        return real(bot, kind, payload)

    monkeypatch.setattr(app.state.computers, "send_input", slow_send_input)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as session:
        started = time.monotonic()
        typing = asyncio.create_task(
            session.post(
                f"/v1/computer/{bot_id}/input",
                headers=auth_header,
                json={"kind": "clipboard", "payload": {"text": "hello"}},
            )
        )
        await asyncio.sleep(0.05)
        health = await session.get("/health")
        waited = time.monotonic() - started
        assert health.status_code == 200
        assert waited < 0.25, f"health waited {waited:.2f}s behind a 0.45s input"
        typed = await typing
        assert typed.status_code == 200
