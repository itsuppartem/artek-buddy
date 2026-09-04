from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.request
from urllib.parse import quote

import pytest

from artek_buddy.auth import derive_credential_executor_token
from artek_buddy.supervisor.docker_engine import DockerEngine

pytestmark = pytest.mark.live


def _request(token: str, body: bytes) -> dict:
    request = urllib.request.Request(
        "http://127.0.0.1:7091/credential-executions",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=75) as response:
        return json.loads(response.read())


def test_runner_has_pinned_auth_tools_and_leaves_no_container() -> None:
    host_token = os.environ["AGENT_HTTP_TOKEN"]
    fixture = "ghp_" + ("R" * 36)
    body = json.dumps(
        {
            "bot_id": f"bot_{secrets.token_hex(8)}",
            "home_key": f"credential-{secrets.token_hex(6)}",
            "command": (
                "gh --version && uv --version && env && "
                'test -n "$GH_TOKEN" && '
                'printf "%s\\n" "$GH_TOKEN"'
            ),
            "cwd": ".",
            "timeout_seconds": 30,
            "injected_env": {"GH_TOKEN": fixture},
        }
    ).encode()
    with pytest.raises(urllib.error.HTTPError) as rejected:
        _request(host_token, body)
    assert rejected.value.code == 401

    result = _request(derive_credential_executor_token(host_token), body)
    assert result["ok"] is True
    assert "gh version 2.99.0" in result["stdout"]
    assert "uv 0.12.9" in result["stdout"]
    assert "HOME=/workspace" in result["stdout"]
    assert "PYTHON_VERSION=" not in result["stdout"]
    assert "AGENT_HTTP_TOKEN=" not in result["stdout"]
    assert fixture not in json.dumps(result)
    assert "[redacted]" in result["stdout"]

    status, runners = DockerEngine().request(
        "GET",
        "/containers/json?all=1&filters="
        + quote(json.dumps({"label": ["artek.kind=credential-runner"]})),
    )
    assert status == 200
    assert runners == []
