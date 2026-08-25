from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.api.helpers import create_bot, wait_run, wait_run_status

from artek_buddy.db.shaping import isoformat_utc
from artek_buddy.main import app


def _bot_record(bot_id: str):
    bot = app.state.store.get_bot(bot_id)
    assert bot is not None
    return bot, app.state.store.get_computer_for_bot(bot)


def _set_sleep_at(bot_id: str, when: datetime) -> str:
    bot, record = _bot_record(bot_id)
    record.sleep_at = isoformat_utc(when)
    app.state.store.save_computer(record)
    return app.state.store.get_computer_for_bot(bot).sleep_at or ""


def test_heartbeat_does_not_refresh_sleep_at(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdleBeat", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    stamped = _set_sleep_at(bot_id, datetime.now(UTC) - timedelta(minutes=4))
    beat = client.post(f"/v1/computer/{bot_id}/heartbeat", headers=auth_header)
    assert beat.status_code == 200
    _bot, after = _bot_record(bot_id)
    assert after.sleep_at == stamped


def test_owner_input_refreshes_sleep_at(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdleType", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    taken = client.post(f"/v1/computer/{bot_id}/takeover", headers=auth_header)
    assert taken.status_code == 200
    stamped = _set_sleep_at(bot_id, datetime.now(UTC) - timedelta(minutes=4))
    typed = client.post(
        f"/v1/computer/{bot_id}/input",
        headers=auth_header,
        json={"kind": "key", "payload": {"text": "a"}},
    )
    assert typed.status_code == 200
    _bot, after = _bot_record(bot_id)
    assert after.sleep_at
    assert after.sleep_at > stamped
    assert after.control_holder == "user"


def test_idle_takeover_releases_like_release(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdleHands", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    taken = client.post(f"/v1/computer/{bot_id}/takeover", headers=auth_header)
    assert taken.status_code == 200
    bot, record = _bot_record(bot_id)
    record.last_input_at = isoformat_utc(datetime.now(UTC) - timedelta(minutes=3))
    app.state.store.save_computer(record)
    status = client.get(f"/v1/computer/{bot_id}", headers=auth_header)
    assert status.status_code == 200
    assert status.json()["control_holder"] == "bot"
    assert app.state.store.get_computer_for_bot(bot).control_holder == "bot"


def test_recent_input_keeps_takeover(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdleMove", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    assert client.post(f"/v1/computer/{bot_id}/takeover", headers=auth_header).status_code == 200
    status = client.get(f"/v1/computer/{bot_id}", headers=auth_header)
    assert status.status_code == 200
    assert status.json()["control_holder"] == "user"


def test_heartbeat_does_not_refresh_last_input_at(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdleBeatHold", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    assert client.post(f"/v1/computer/{bot_id}/takeover", headers=auth_header).status_code == 200
    _bot, before = _bot_record(bot_id)
    stamped = before.last_input_at or ""
    assert stamped
    beat = client.post(f"/v1/computer/{bot_id}/heartbeat", headers=auth_header)
    assert beat.status_code == 200
    _bot, after = _bot_record(bot_id)
    assert after.last_input_at == stamped
    assert after.control_holder == "user"


def test_screen_poll_does_not_refresh_sleep_at(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdleScreen", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    stamped = _set_sleep_at(bot_id, datetime.now(UTC) - timedelta(minutes=4))
    screen = client.get(f"/v1/computer/{bot_id}/screen", headers=auth_header)
    assert screen.status_code == 200
    _bot, after = _bot_record(bot_id)
    assert after.sleep_at == stamped


def test_boot_sets_sleep_at_in_the_future(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdleBoot", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    _bot, record = _bot_record(bot_id)
    assert record.sleep_at
    assert record.sleep_at > isoformat_utc()


def test_desktop_observe_refreshes_sleep_at(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdleObserve", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    stamped = _set_sleep_at(bot_id, datetime.now(UTC) - timedelta(minutes=4))
    bot, _record = _bot_record(bot_id)
    app.state.computers.observe(bot)
    _bot, after = _bot_record(bot_id)
    assert after.sleep_at
    assert after.sleep_at > stamped


def test_activity_input_refreshes_sleep_and_skips_supervisor(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdleActivity", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    assert client.post(f"/v1/computer/{bot_id}/takeover", headers=auth_header).status_code == 200
    stamped = _set_sleep_at(bot_id, datetime.now(UTC) - timedelta(minutes=4))
    bot, record = _bot_record(bot_id)
    record.last_input_at = isoformat_utc(datetime.now(UTC) - timedelta(minutes=1))
    app.state.store.save_computer(record)
    before = app.state.store.get_computer_for_bot(bot).last_input_at or ""
    typed = client.post(
        f"/v1/computer/{bot_id}/input",
        headers=auth_header,
        json={"kind": "activity", "payload": {}},
    )
    assert typed.status_code == 200
    _bot, after = _bot_record(bot_id)
    assert after.control_holder == "user"
    assert after.last_input_at
    assert after.last_input_at > before
    assert after.sleep_at
    assert after.sleep_at > stamped
    calls = [call for call in app.state.computers.client.calls if call[0] == "input"]
    assert all(call[1] != "activity" for call in calls)


def test_hard_takeover_lease_still_expires_to_none(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdleHardLease", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    assert client.post(f"/v1/computer/{bot_id}/takeover", headers=auth_header).status_code == 200
    bot, record = _bot_record(bot_id)
    record.control_lease_expires_at = isoformat_utc(datetime.now(UTC) - timedelta(minutes=1))
    record.last_input_at = isoformat_utc()
    app.state.store.save_computer(record)
    status = client.get(f"/v1/computer/{bot_id}", headers=auth_header)
    assert status.status_code == 200
    assert status.json()["control_holder"] == "none"
    assert app.state.store.get_computer_for_bot(bot).control_holder == "none"


def test_idle_release_does_not_resume_parked_run(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdleNoResume", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-park-takeover"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run"]["id"]
    wait_run_status(client, auth_header, bot_id, run_id, "waiting_takeover")
    assert client.post(f"/v1/computer/{bot_id}/takeover", headers=auth_header).status_code == 200
    bot, record = _bot_record(bot_id)
    record.last_input_at = isoformat_utc(datetime.now(UTC) - timedelta(minutes=3))
    app.state.store.save_computer(record)
    status = client.get(f"/v1/computer/{bot_id}", headers=auth_header)
    assert status.status_code == 200
    assert status.json()["control_holder"] == "bot"
    snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert snap.status_code == 200
    run = snap.json().get("run") or {}
    assert run.get("id") == run_id
    assert run.get("status") == "waiting_takeover"
    listed = client.get(f"/v1/bots/{bot_id}", headers=auth_header)
    assert listed.status_code == 200
    assert listed.json()["status"] == "waiting_takeover"
    assert app.state.store.get_computer_for_bot(bot).control_holder == "bot"


def test_forgotten_takeover_can_idle_sleep_after_release(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdleThenSleep", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    assert client.post(f"/v1/computer/{bot_id}/takeover", headers=auth_header).status_code == 200
    bot, record = _bot_record(bot_id)
    record.last_input_at = isoformat_utc(datetime.now(UTC) - timedelta(minutes=3))
    record.sleep_at = isoformat_utc(datetime.now(UTC) - timedelta(minutes=1))
    app.state.store.save_computer(record)
    assert bot_id not in app.state.store.due_idle_computer_bots()
    released = app.state.store.expire_idle_takeovers(120)
    assert released >= 1
    assert app.state.store.get_computer_for_bot(bot).control_holder == "bot"
    assert bot_id in app.state.store.due_idle_computer_bots()


def test_driving_run_blocks_idle_sleep(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdleDrive", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-slow now"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run"]["id"]
    wait_run_status(client, auth_header, bot_id, run_id, "running")
    _set_sleep_at(bot_id, datetime.now(UTC) - timedelta(minutes=1))
    due = app.state.store.due_idle_computer_bots()
    assert bot_id not in due
    wait_run(client, auth_header, bot_id, run_id)


def test_parked_takeover_does_not_block_idle_sleep(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "IdlePark", computer_mode="dedicated")["id"]
    assert client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header).status_code == 200
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-park-takeover"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run"]["id"]
    wait_run_status(client, auth_header, bot_id, run_id, "waiting_takeover")
    _set_sleep_at(bot_id, datetime.now(UTC) - timedelta(minutes=1))
    due = app.state.store.due_idle_computer_bots()
    assert bot_id in due
