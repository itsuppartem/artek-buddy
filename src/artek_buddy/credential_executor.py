"""Internal loopback command runner with no credential-storage mount."""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ForkingMixIn
from typing import Any, BinaryIO, cast
from urllib.parse import urlparse

from artek_buddy.auth import derive_credential_executor_token, host_token_match
from artek_buddy.bot_credentials import (
    CredentialExecutionResult,
    normalized_credential_env,
)
from artek_buddy.observe import configure_logging

log = logging.getLogger("artek_buddy.credential_executor")

_MAX_BODY_BYTES = 512 * 1024
_MAX_COMMAND_CHARS = 16_000
_MAX_CWD_CHARS = 512
_MAX_OUTPUT_BYTES = 64 * 1024
_MAX_TIMEOUT_SECONDS = 60.0
_MIN_TIMEOUT_SECONDS = 0.1
_BOT_ID = re.compile(r"^bot_[0-9a-f]{16}$")
_HOME_KEY = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class CredentialExecutorError(RuntimeError):
    pass


def credential_executor_authorized(header: str, token: str) -> bool:
    scheme, separator, provided = (header or "").partition(" ")
    if scheme != "Bearer" or not separator or not provided:
        return False
    return host_token_match(provided, token)


def _contained_cwd(homes_root: Path, home_key: str, cwd: str) -> Path:
    if not _HOME_KEY.fullmatch(home_key or ""):
        raise ValueError("invalid home key")
    relative = (cwd or ".").strip() or "."
    if len(relative) > _MAX_CWD_CHARS or "\x00" in relative or Path(relative).is_absolute():
        raise ValueError("cwd must be relative to this bot home")
    root = homes_root.resolve()
    # Both joins are constrained and resolved before subprocess use.
    # codeql[py/path-injection]
    home = (root / home_key).resolve()  # lgtm[py/path-injection]
    target = (home / relative).resolve()  # lgtm[py/path-injection]
    if not home.is_relative_to(root) or not target.is_relative_to(home):
        raise ValueError("cwd must stay under this bot home")
    if not home.is_dir() or not target.is_dir():
        raise ValueError("cwd does not exist under this bot home")
    return target


def _redact(value: str, stored: list[str]) -> str:
    out = value
    for secret in sorted({item for item in stored if item}, key=len, reverse=True):
        out = out.replace(secret, "[redacted]")
    return out


def _drain(stream: BinaryIO, chunks: list[bytes], state: dict[str, bool]) -> None:
    kept = 0
    while True:
        chunk = stream.read(8192)
        if not chunk:
            return
        room = _MAX_OUTPUT_BYTES - kept
        if room > 0:
            chunks.append(chunk[:room])
            kept += min(room, len(chunk))
        if len(chunk) > room:
            state["truncated"] = True


def execute_credential_command(
    *,
    homes_root: str | Path,
    bot_id: str,
    home_key: str,
    command: str,
    cwd: str = ".",
    timeout_seconds: float = 30,
    injected_env: dict[str, str],
    redacted_secrets: list[str],
) -> CredentialExecutionResult:
    if not _BOT_ID.fullmatch((bot_id or "").strip()):
        raise ValueError("invalid bot id")
    text = (command or "").strip()
    if not text:
        raise ValueError("command is required")
    if len(text) > _MAX_COMMAND_CHARS or "\x00" in text:
        raise ValueError("command is too long")
    for name in injected_env:
        if normalized_credential_env(name.lower(), name) != name:
            raise ValueError("invalid credential environment name")
    workdir = _contained_cwd(Path(homes_root), home_key, cwd)
    timeout = max(_MIN_TIMEOUT_SECONDS, min(float(timeout_seconds), _MAX_TIMEOUT_SECONDS))
    env = {
        "HOME": str((Path(homes_root).resolve() / home_key).resolve()),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_TERMINAL_PROMPT": "0",
    }
    env.update(injected_env)
    try:
        # The model-authorized command is the intentional execution boundary.
        # codeql[py/command-line-injection]
        process = subprocess.Popen(  # noqa: S603  # lgtm[py/command-line-injection]
            ["/bin/sh", "-lc", text],
            cwd=str(workdir),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as err:
        return CredentialExecutionResult(
            ok=False,
            exit_code=127,
            stdout="",
            stderr="",
            error=_redact(str(err), redacted_secrets),
        )

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    stdout_state = {"truncated": False}
    stderr_state = {"truncated": False}
    stdout_pipe = cast(BinaryIO, process.stdout)
    stderr_pipe = cast(BinaryIO, process.stderr)
    readers = [
        threading.Thread(
            target=_drain,
            args=(stdout_pipe, stdout_chunks, stdout_state),
            daemon=True,
        ),
        threading.Thread(
            target=_drain,
            args=(stderr_pipe, stderr_chunks, stderr_state),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)
    finally:
        # A shell that exits after starting a background job must not leave that
        # job running past this bounded request.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for reader in readers:
            reader.join(timeout=2)
        stdout_pipe.close()
        stderr_pipe.close()

    truncated = stdout_state["truncated"] or stderr_state["truncated"]
    stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")
    stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
    if stdout_state["truncated"]:
        stdout += "\n[output truncated]"
    if stderr_state["truncated"]:
        stderr += "\n[output truncated]"
    error = f"command timed out after {timeout:g}s" if timed_out else ""
    return CredentialExecutionResult(
        ok=process.returncode == 0 and not timed_out,
        exit_code=124 if timed_out else int(process.returncode or 0),
        stdout=_redact(stdout, redacted_secrets),
        stderr=_redact(stderr, redacted_secrets),
        timed_out=timed_out,
        truncated=truncated,
        error=_redact(error, redacted_secrets),
    )


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
        # The constructor URL is restricted to loopback HTTP above.
        request = urllib.request.Request(  # noqa: S310
            f"{self.base_url}/v1/execute",
            data=json.dumps(
                {
                    "bot_id": bot_id,
                    "home_key": home_key,
                    "command": command,
                    "cwd": cwd,
                    "timeout_seconds": timeout_seconds,
                    "injected_env": injected_env,
                    "redacted_secrets": redacted_secrets,
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
                request, timeout=max(self.timeout, min(float(timeout_seconds), 60) + 2)
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as err:
            try:
                body = json.loads(err.read().decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                body = {}
            detail = str(body.get("error") or "credential executor rejected the request")
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


class _CredentialExecutorHandler(BaseHTTPRequestHandler):
    server_version = "ArtekCredentialExecutor/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        log.info(fmt, *args)

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("invalid content length") from None
        if length < 0 or length > _MAX_BODY_BYTES:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("invalid JSON") from None
        if not isinstance(body, dict):
            raise ValueError("invalid JSON")
        return body

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/health":
            self._json(200, {"ok": True})
            return
        self._json(404, {"ok": False})

    def do_POST(self) -> None:
        expected = str(self.server.token)  # type: ignore[attr-defined]
        if not credential_executor_authorized(self.headers.get("Authorization", ""), expected):
            self._json(403, {"error": "invalid executor token"})
            return
        try:
            body = self._body()
            if urlparse(self.path).path != "/v1/execute":
                self._json(404, {"error": "not found"})
                return
            raw_env = body.get("injected_env")
            raw_secrets = body.get("redacted_secrets")
            if not isinstance(raw_env, dict) or not isinstance(raw_secrets, list):
                raise ValueError("invalid execution environment")
            injected_env = {
                str(name): str(value)
                for name, value in raw_env.items()
                if isinstance(name, str) and isinstance(value, str)
            }
            if len(injected_env) != len(raw_env):
                raise ValueError("invalid execution environment")
            redacted = [str(value) for value in raw_secrets if isinstance(value, str)]
            if len(redacted) != len(raw_secrets):
                raise ValueError("invalid redaction values")
            result = execute_credential_command(
                homes_root=self.server.homes_root,  # type: ignore[attr-defined]
                bot_id=str(body.get("bot_id") or ""),
                home_key=str(body.get("home_key") or ""),
                command=str(body.get("command") or ""),
                cwd=str(body.get("cwd") or "."),
                timeout_seconds=float(body.get("timeout_seconds") or 30),
                injected_env=injected_env,
                redacted_secrets=redacted,
            )
            self._json(200, asdict(result))
        except (TypeError, ValueError) as err:
            self._json(400, {"error": str(err)})
        except Exception:
            log.exception("credential executor operation failed")
            self._json(500, {"error": "credential executor error"})


class _ForkingHTTPServer(ForkingMixIn, HTTPServer):
    max_children = 8
    block_on_close = True


def make_credential_executor_server(
    *,
    token: str,
    homes_root: str | Path,
    port: int = 8432,
    forking: bool = True,
) -> HTTPServer:
    if not token:
        raise ValueError("credential executor token is required")
    server_type = _ForkingHTTPServer if forking else HTTPServer
    server = server_type(("127.0.0.1", port), _CredentialExecutorHandler)
    server.token = token  # type: ignore[attr-defined]
    server.homes_root = Path(homes_root)  # type: ignore[attr-defined]
    return server


def main() -> int:
    explicit = os.environ.get("CREDENTIAL_EXECUTOR_TOKEN", "").strip()
    host_token = os.environ.get("AGENT_HTTP_TOKEN", "").strip()
    if host_token:
        clean_env = dict(os.environ)
        clean_env.pop("AGENT_HTTP_TOKEN", None)
        clean_env["CREDENTIAL_EXECUTOR_TOKEN"] = explicit or derive_credential_executor_token(
            host_token
        )
        os.execve(  # noqa: S606
            sys.executable,
            [sys.executable, "-m", "artek_buddy", "credential-executor"],
            clean_env,
        )
    configure_logging()
    if not explicit:
        log.error("credential executor token is not configured")
        return 2
    port = int(os.environ.get("CREDENTIAL_EXECUTOR_PORT", "8432"))
    homes = os.environ.get("CREDENTIAL_EXECUTOR_HOMES_DIR", "/homes")
    server = make_credential_executor_server(token=explicit, homes_root=homes, port=port)
    log.info("credential executor listening on 127.0.0.1:%s", port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0
