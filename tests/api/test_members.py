from __future__ import annotations


def test_fresh_db_has_owner_member(client, auth_header) -> None:
    response = client.get("/v1/me", headers=auth_header)
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "usr_owner"
    assert body["role"] == "owner"
    assert body["is_deployment_owner"] is True
    assert body["member"] is not None
    assert body["member"]["id"] == "mem_owner"
    assert body["member"]["name"] == "Owner"
    assert body["member"]["role"] == "owner"
    assert body["member"]["state"] == "active"
    assert isinstance(body["devices"], list)


def test_pairing_device_attaches_to_owner_and_me_lists_it(client, host_token) -> None:
    # 1. Mint pairing code using host token
    code_res = client.post(
        "/v1/devices/pairing",
        headers={"Authorization": f"Bearer {host_token}"},
    )
    assert code_res.status_code == 200
    code = code_res.json()["code"]

    # 2. Pair device A
    dev_a = client.post(
        "/v1/devices",
        json={"name": "PhoneDevice", "platform": "web", "pairing_code": code},
    )
    assert dev_a.status_code == 200
    data_a = dev_a.json()
    token_a = data_a["token"]
    dev_a_id = data_a["id"]
    assert data_a["member_id"] == "mem_owner"

    # 3. GET /v1/me using device A's bearer token
    me_res = client.get("/v1/me", headers={"Authorization": f"Bearer {token_a}"})
    assert me_res.status_code == 200
    me = me_res.json()
    assert me["member"]["id"] == "mem_owner"
    assert me["role"] == "owner"
    active_device_ids = {d["id"] for d in me["devices"]}
    assert dev_a_id in active_device_ids


def test_pair_second_device_and_owner_revokes_first(client, host_token) -> None:
    # 1. Pair Device A
    code_a = client.post(
        "/v1/devices/pairing",
        headers={"Authorization": f"Bearer {host_token}"},
    ).json()["code"]
    dev_a = client.post(
        "/v1/devices",
        json={"name": "FirstDevice", "platform": "linux", "pairing_code": code_a},
    ).json()
    token_a = dev_a["token"]
    id_a = dev_a["id"]

    # 2. Pair Device B
    code_b = client.post(
        "/v1/devices/pairing",
        headers={"Authorization": f"Bearer {host_token}"},
    ).json()["code"]
    dev_b = client.post(
        "/v1/devices",
        json={"name": "SecondDevice", "platform": "web", "pairing_code": code_b},
    ).json()
    token_b = dev_b["token"]
    id_b = dev_b["id"]

    # Both devices initially work
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {token_a}"}).status_code == 200
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {token_b}"}).status_code == 200

    # 3. Device B cannot revoke Device A (device tokens cannot revoke other devices)
    stolen = client.delete(
        f"/v1/devices/{id_a}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert stolen.status_code == 403

    # 4. Owner revokes Device A via host token
    del_res = client.delete(
        f"/v1/devices/{id_a}", headers={"Authorization": f"Bearer {host_token}"}
    )
    assert del_res.status_code == 200
    assert del_res.json()["revoked_at"] is not None

    # 5. Device A is now revoked and fails auth
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {token_a}"}).status_code == 403

    # 6. Device B remains active and authenticated
    me_b = client.get("/v1/me", headers={"Authorization": f"Bearer {token_b}"})
    assert me_b.status_code == 200
    # Revoked device is omitted from active devices list in /v1/me
    active_ids = {d["id"] for d in me_b.json()["devices"]}
    assert id_a not in active_ids
    assert id_b in active_ids


def test_suspended_member_disallows_all_devices(client, host_token) -> None:
    store = client.app.state.store

    code = client.post(
        "/v1/devices/pairing",
        headers={"Authorization": f"Bearer {host_token}"},
    ).json()["code"]
    dev = client.post(
        "/v1/devices",
        json={"name": "TabletDevice", "platform": "web", "pairing_code": code},
    ).json()
    token = dev["token"]

    # Device works
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    # Suspend owner member
    store.suspend_member("mem_owner")
    try:
        # Auth fails for device
        res = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 403
    finally:
        # Reactivate owner
        store.activate_member("mem_owner")

    # Works again after reactivation
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
