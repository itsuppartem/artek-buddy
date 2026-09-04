"""Broker client for supervisor-orchestrated credential runner containers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from artek_buddy.bot_credentials import CredentialExecutionResult


class CredentialExecutorError(RuntimeError):
    pass


class CredentialExecutorClient:
    def __init__(self, base_url: str, token: str, timeout: float = 2.0) -> None:
        base = (base_url or "").rstrip("/")
        parsed = urlparse(base)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("credential executor URL must be loopback http")
        self.base_url = base
        self.token = token
        self.timeout = timeout

    def execute(
        self,
        *,
        bot_id: str,
        home_key: str,
        command: str,
        cwd: str,
        timeout_seconds: float,
        injected_env: dict[str, str],
        redacted_secrets: list[str],
    ) -> CredentialExecutionResult:
        del redacted_secrets
        request = urllib.request.Request(  # noqa: S310
            f"{self.base_url}/credential-executions",
            data=json.dumps(
                {
                    "bot_id": bot_id,
                    "home_key": home_key,
                    "command": command,
                    "cwd": cwd,
                    "timeout_seconds": timeout_seconds,
                    "injected_env": injected_env,
                }
            ).encode(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310
                request,
                timeout=max(self.timeout, min(float(timeout_seconds), 60) + 5),
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as err:
            detail = _error_detail(err)
            if err.code == 400:
                raise ValueError(detail) from err
            raise CredentialExecutorError(detail) from err
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise CredentialExecutorError("credential executor unavailable") from err
        try:
            body = json.loads(raw.decode()) if raw else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise CredentialExecutorError("credential executor returned invalid JSON") from err
        if not isinstance(body, dict):
            raise CredentialExecutorError("credential executor returned invalid JSON")
        return CredentialExecutionResult(
            ok=bool(body.get("ok")),
            exit_code=int(body.get("exit_code") or 0),
            stdout=str(body.get("stdout") or ""),
            stderr=str(body.get("stderr") or ""),
            timed_out=bool(body.get("timed_out")),
            truncated=bool(body.get("truncated")),
            error=str(body.get("error") or ""),
        )


def _error_detail(err: urllib.error.HTTPError) -> str:
    try:
        body: Any = json.loads(err.read().decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}
    if not isinstance(body, dict):
        return "credential executor rejected the request"
    return str(body.get("error") or "credential executor rejected the request")
