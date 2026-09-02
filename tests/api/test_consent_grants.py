from __future__ import annotations

from tests.api.helpers import consent_id_from_thread, create_bot, wait_run, wait_run_status
from tests.support import mask_secret

from artek_buddy.runtime.types import TurnContext


def _mint_device(client, auth_header: dict[str, str], name: str) -> dict[str, str]:
    minted = client.post("/v1/devices/pairing", headers=auth_header)
    assert minted.status_code == 200, minted.text
    created = client.post(
        "/v1/devices",
        json={"name": name, "platform": "linux", "pairing_code": minted.json()["code"]},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    mask_secret(body["token"])
    return body


def test_grant_lookup_is_this_device_or_host_wide_not_any_row(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "GrantLookup")["id"]
    store = client.app.state.store
    store.save_consent_grant(bot_id, "browse", "https://example.com", device_id="dev_a")
    assert store.find_consent_grant(bot_id, "browse", "https://example.com", "dev_a")
    assert store.find_consent_grant(bot_id, "browse", "https://example.com", "dev_b") is None
    assert store.find_consent_grant(bot_id, "browse", "https://example.com", None) is None
    store.save_consent_grant(bot_id, "browse", "https://example.com", device_id=None)
    assert store.find_consent_grant(bot_id, "browse", "https://example.com", None)
    assert store.find_consent_grant(bot_id, "browse", "https://example.com", "dev_b")


def test_two_devices_cannot_spend_each_others_always(client, auth_header) -> None:
    bot = create_bot(client, auth_header, "GrantDevices")
    first = _mint_device(client, auth_header, "Deb")
    second = _mint_device(client, auth_header, "Phone")
    store = client.app.state.store
    hub = client.app.state.consent
    runtime = client.app.state.runtime
    store.save_consent_grant(
        bot["id"],
        "browse",
        "https://example.com",
        device_id=first["id"],
    )
    lead = TurnContext(
        bot_id=bot["id"],
        run_id="run_first",
        thread_id=bot["thread_id"],
        role="lead",
        device_id=first["id"],
    )
    other = TurnContext(
        bot_id=bot["id"],
        run_id="run_second",
        thread_id=bot["thread_id"],
        role="lead",
        device_id=second["id"],
    )
    runtime.freeze_turn(lead)
    runtime.freeze_turn(other)
    runtime.set_turn_device(first["id"])
    first_tokens = runtime.apply_callback_context(lead)
    try:
        assert hub.has_grant(
            bot["id"],
            "browse",
            "https://example.com",
            runtime.resolve_turn_device(),
        )
    finally:
        runtime.reset_callback_context(first_tokens)
    second_tokens = runtime.apply_callback_context(other)
    try:
        assert not hub.has_grant(
            bot["id"],
            "browse",
            "https://example.com",
            runtime.resolve_turn_device(),
        )
    finally:
        runtime.reset_callback_context(second_tokens)


def test_follow_up_after_other_device_keeps_live_grant_device(client, auth_header) -> None:
    bot = create_bot(client, auth_header, "GrantFollowUp")
    first = _mint_device(client, auth_header, "DebFollow")
    second = _mint_device(client, auth_header, "PhoneFollow")
    runtime = client.app.state.runtime
    sent = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers={"Authorization": f"Bearer {first['token']}"},
        json={"text": "e2e-consent-browse"},
    )
    assert sent.status_code == 200, sent.text
    run_id = sent.json()["run_id"]
    wait_run_status(client, auth_header, bot["id"], run_id, "waiting_input")
    live = runtime.resolve_turn(bot["id"])
    assert live is not None
    assert live.run_id == run_id
    assert live.device_id == first["id"]
    follow = client.post(
        f"/v1/threads/{bot['id']}/follow-up",
        headers={"Authorization": f"Bearer {second['token']}"},
        json={"text": "status?"},
    )
    assert follow.status_code == 200, follow.text
    still = runtime.resolve_turn(bot["id"])
    assert still is not None
    assert still.run_id == run_id
    tokens = runtime.apply_callback_context(still)
    try:
        assert runtime.resolve_turn_device() == first["id"]
    finally:
        runtime.reset_callback_context(tokens)
    snap = client.get(f"/v1/threads/{bot['id']}", headers=auth_header)
    assert snap.status_code == 200, snap.text
    consent_id = consent_id_from_thread(snap.json())
    denied = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "deny"},
    )
    assert denied.status_code == 200, denied.text
    finished = wait_run(client, auth_header, bot["id"], run_id)
    assert finished["run"]["status"] == "failed"
