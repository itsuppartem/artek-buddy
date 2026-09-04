"""Loopback credential storage and credential-scoped command dispatch."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from artek_buddy.auth import (
    credential_broker_token,
    derive_credential_executor_token,
    host_token_match,
)
from artek_buddy.bot_credentials import (
    BotCredentialStatus,
    CredentialExecutionResult,
    CredentialStoreError,
    CredentialStoreUnavailable,
    InMemoryCredentialStore,
    credential_env,
    last_four,
    normalized_credential_env,
    provider_slug,
)
from artek_buddy.credential_executor import (
    CredentialExecutorClient,
    CredentialExecutorError,
)
from artek_buddy.db.shaping import isoformat_utc
from artek_buddy.observe import configure_logging

log = logging.getLogger("artek_buddy.credential_broker")

_BOT_ID = re.compile(r"^bot_[0-9a-f]{16}$")
_MAX_BODY_BYTES = 32 * 1024
_MAX_EXECUTION_TIMEOUT_SECONDS = 60.0


def _require_bot_id(bot_id: str) -> str:
    value = (bot_id or "").strip()
    if not _BOT_ID.fullmatch(value):
        raise ValueError("invalid bot id")
    return value


def _require_provider(provider: str) -> str:
    slug = provider_slug(provider)
    if slug is None:
        raise ValueError("unknown provider")
    return slug


def _status(row: sqlite3.Row) -> BotCredentialStatus:
    return BotCredentialStatus(
        provider=str(row["provider"]),
        scope="this_bot",
        last_four=str(row["last_four"]),
        updated_at=str(row["updated_at"]),
        env_name=str(row["env_name"]),
    )


class PrivateCredentialStorage:
    """Broker-owned SQLite store. No app-facing method returns a secret."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.path = self.root / "credentials.sqlite3"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS credentials (
                bot_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                secret TEXT NOT NULL,
                last_four TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                env_name TEXT NOT NULL,
                PRIMARY KEY (bot_id, provider)
            )
            """
        )
        self._conn.commit()
        os.chmod(self.path, 0o600)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def put(
        self,
        bot_id: str,
        provider: str,
        secret: str,
        env_name: str = "",
    ) -> BotCredentialStatus:
        bot = _require_bot_id(bot_id)
        slug = _require_provider(provider)
        value = (secret or "").strip()
        if not value:
            raise ValueError("secret is empty")
        if len(value) > 8000:
            raise ValueError("secret is too long")
        env = normalized_credential_env(slug, env_name)
        stamp = isoformat_utc()
        with self._lock:
            # Plaintext-at-rest is confined to the broker volume and named in THREAT-MODEL.md.
            # codeql[py/clear-text-storage-sensitive-data]
            self._conn.execute(  # lgtm[py/clear-text-storage-sensitive-data]
                """
                INSERT INTO credentials
                    (bot_id, provider, secret, last_four, updated_at, env_name)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(bot_id, provider) DO UPDATE SET
                    secret = excluded.secret,
                    last_four = excluded.last_four,
                    updated_at = excluded.updated_at,
                    env_name = excluded.env_name
                """,
                (bot, slug, value, last_four(value), stamp, env),
            )
            self._conn.commit()
        return BotCredentialStatus(
            provider=slug,
            scope="this_bot",
            last_four=last_four(value),
            updated_at=stamp,
            env_name=env,
        )

    def list_for_bot(self, bot_id: str) -> list[BotCredentialStatus]:
        bot = _require_bot_id(bot_id)
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT provider, last_four, updated_at, env_name
                FROM credentials
                WHERE bot_id = ?
                ORDER BY CASE provider WHEN 'github' THEN 0 WHEN 'pypi' THEN 1 ELSE 50 END,
                         provider
                """,
                (bot,),
            ).fetchall()
        return [_status(row) for row in rows]

    def forget(self, bot_id: str, provider: str) -> bool:
        bot = _require_bot_id(bot_id)
        slug = _require_provider(provider)
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM credentials WHERE bot_id = ? AND provider = ?",
                (bot, slug),
            )
            self._conn.commit()
        return bool(cursor.rowcount)

    def forget_bot(self, bot_id: str) -> None:
        bot = _require_bot_id(bot_id)
        with self._lock:
            self._conn.execute("DELETE FROM credentials WHERE bot_id = ?", (bot,))
            self._conn.commit()

    def execution_material(self, bot_id: str) -> tuple[dict[str, str], list[str], list[str]]:
        bot = _require_bot_id(bot_id)
        with self._lock:
            bot_rows = self._conn.execute(
                """
                SELECT provider, secret, last_four, updated_at, env_name
                FROM credentials WHERE bot_id = ?
                """,
                (bot,),
            ).fetchall()
            all_rows = self._conn.execute("SELECT secret FROM credentials").fetchall()
        mapped = [
            (
                BotCredentialStatus(
                    provider=str(row["provider"]),
                    scope="this_bot",
                    last_four=str(row["last_four"]),
                    updated_at=str(row["updated_at"]),
                    env_name=str(row["env_name"]),
                ),
                str(row["secret"]),
            )
            for row in bot_rows
        ]
        current = [secret for _row, secret in mapped]
        return credential_env(mapped), current, [str(row["secret"]) for row in all_rows]

    def redaction_values(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT secret FROM credentials").fetchall()
        return [str(row["secret"]) for row in rows]

    def confirm_secret(self, bot_id: str, provider: str, expected: str) -> bool:
        bot = _require_bot_id(bot_id)
        slug = _require_provider(provider)
        with self._lock:
            row = self._conn.execute(
                "SELECT secret FROM credentials WHERE bot_id = ? AND provider = ?",
                (bot, slug),
            ).fetchone()
        return row is not None and secrets.compare_digest(str(row["secret"]), expected)


def _redact(value: str, stored: list[str]) -> str:
    out = value
    for secret in sorted({item for item in stored if item}, key=len, reverse=True):
        out = out.replace(secret, "[redacted]")
    return out


def _redact_result(
    result: CredentialExecutionResult,
    stored: list[str],
) -> CredentialExecutionResult:
    return CredentialExecutionResult(
        ok=result.ok,
        exit_code=result.exit_code,
        stdout=_redact(result.stdout, stored),
        stderr=_redact(result.stderr, stored),
        timed_out=result.timed_out,
        truncated=result.truncated,
        error=_redact(result.error, stored),
    )


class CredentialBrokerClient:
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
            raise ValueError("credential broker URL must be loopback http")
        self.base_url = base
        self.token = token
        self.timeout = timeout

    def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        # The constructor URL is restricted to loopback HTTP above.
        request = urllib.request.Request(  # noqa: S310
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=timeout or self.timeout
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as err:
            try:
                body = json.loads(err.read().decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                body = {}
            detail = str(body.get("error") or "credential broker rejected the request")
            if err.code == 400:
                raise ValueError(detail) from err
            raise CredentialStoreError(detail) from err
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise CredentialStoreUnavailable("credential broker unavailable") from err
        try:
            value = json.loads(raw.decode()) if raw else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise CredentialStoreError("credential broker returned invalid JSON") from err
        if not isinstance(value, dict):
            raise CredentialStoreError("credential broker returned invalid JSON")
        return value

    @staticmethod
    def _row(value: dict[str, Any]) -> BotCredentialStatus:
        return BotCredentialStatus(
            provider=str(value.get("provider") or ""),
            scope="this_bot",
            last_four=str(value.get("last_four") or ""),
            updated_at=str(value.get("updated_at") or ""),
            env_name=str(value.get("env_name") or ""),
        )

    def put(
        self,
        bot_id: str,
        provider: str,
        secret: str,
        env_name: str = "",
    ) -> BotCredentialStatus:
        body = self._post(
            "/v1/credentials/put",
            {
                "bot_id": bot_id,
                "provider": provider,
                "secret": secret,
                "env_name": env_name,
            },
        )
        return self._row(body)

    def list_for_bot(self, bot_id: str) -> list[BotCredentialStatus]:
        body = self._post("/v1/credentials/list", {"bot_id": bot_id})
        rows = body.get("credentials")
        if not isinstance(rows, list):
            raise CredentialStoreError("credential broker returned invalid metadata")
        return [self._row(row) for row in rows if isinstance(row, dict)]

    def forget(self, bot_id: str, provider: str) -> bool:
        body = self._post(
            "/v1/credentials/delete",
            {"bot_id": bot_id, "provider": provider},
        )
        return bool(body.get("deleted"))

    def forget_bot(self, bot_id: str) -> None:
        self._post("/v1/credentials/delete-bot", {"bot_id": bot_id})

    def execute(
        self,
        bot_id: str,
        home_key: str,
        command: str,
        *,
        cwd: str = ".",
        timeout_seconds: float = 30,
    ) -> CredentialExecutionResult:
        body = self._post(
            "/v1/credentials/execute",
            {
                "bot_id": bot_id,
                "home_key": home_key,
                "command": command,
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
            },
            timeout=max(
                self.timeout,
                min(float(timeout_seconds), _MAX_EXECUTION_TIMEOUT_SECONDS) + 2,
            ),
        )
        return CredentialExecutionResult(
            ok=bool(body.get("ok")),
            exit_code=int(body.get("exit_code") or 0),
            stdout=str(body.get("stdout") or ""),
            stderr=str(body.get("stderr") or ""),
            timed_out=bool(body.get("timed_out")),
            truncated=bool(body.get("truncated")),
            error=str(body.get("error") or ""),
        )


def credential_broker_authorized(header: str, token: str) -> bool:
    scheme, separator, provided = (header or "").partition(" ")
    if scheme != "Bearer" or not separator or not provided:
        return False
    return host_token_match(provided, token)


class _CredentialBrokerHandler(BaseHTTPRequestHandler):
    server_version = "ArtekCredentialBroker/1"

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
        if not credential_broker_authorized(self.headers.get("Authorization", ""), expected):
            self._json(403, {"error": "invalid broker token"})
            return
        try:
            body = self._body()
            path = urlparse(self.path).path
            storage: PrivateCredentialStorage = self.server.storage  # type: ignore[attr-defined]
            if path == "/v1/credentials/put":
                row = storage.put(
                    str(body.get("bot_id") or ""),
                    str(body.get("provider") or ""),
                    str(body.get("secret") or ""),
                    env_name=str(body.get("env_name") or ""),
                )
                self._json(200, asdict(row))
                return
            if path == "/v1/credentials/list":
                rows = storage.list_for_bot(str(body.get("bot_id") or ""))
                self._json(200, {"credentials": [asdict(row) for row in rows]})
                return
            if path == "/v1/credentials/delete":
                deleted = storage.forget(
                    str(body.get("bot_id") or ""),
                    str(body.get("provider") or ""),
                )
                self._json(200, {"ok": True, "deleted": deleted})
                return
            if path == "/v1/credentials/delete-bot":
                storage.forget_bot(str(body.get("bot_id") or ""))
                self._json(200, {"ok": True})
                return
            if path == "/v1/credentials/execute":
                bot_id = str(body.get("bot_id") or "")
                injected_env, current, stored = storage.execution_material(bot_id)
                executor: CredentialExecutorClient = self.server.executor  # type: ignore[attr-defined]
                result = executor.execute(
                    bot_id=bot_id,
                    home_key=str(body.get("home_key") or ""),
                    command=str(body.get("command") or ""),
                    cwd=str(body.get("cwd") or "."),
                    timeout_seconds=float(body.get("timeout_seconds") or 30),
                    injected_env=injected_env,
                    redacted_secrets=current,
                )
                self._json(
                    200,
                    asdict(_redact_result(result, stored + storage.redaction_values())),
                )
                return
            self._json(404, {"error": "not found"})
        except (TypeError, ValueError) as err:
            self._json(400, {"error": str(err)})
        except CredentialExecutorError:
            self._json(503, {"error": "credential executor unavailable"})
        except Exception:
            log.exception("credential broker operation failed")
            self._json(500, {"error": "credential broker error"})


def make_credential_broker_server(
    *,
    storage: PrivateCredentialStorage,
    token: str,
    executor: CredentialExecutorClient,
    port: int = 8431,
) -> ThreadingHTTPServer:
    if not token:
        raise ValueError("credential broker token is required")
    server = ThreadingHTTPServer(("127.0.0.1", port), _CredentialBrokerHandler)
    server.storage = storage  # type: ignore[attr-defined]
    server.token = token  # type: ignore[attr-defined]
    server.executor = executor  # type: ignore[attr-defined]
    return server


@dataclass(frozen=True)
class MigrationReport:
    migrated: int = 0
    failed: int = 0


def migrate_legacy_credentials(
    legacy_root: str | Path,
    storage: PrivateCredentialStorage,
) -> MigrationReport:
    root = Path(legacy_root)
    if not root.is_dir():
        return MigrationReport()
    resolved_root = root.resolve()
    migrated = 0
    failed = 0
    for bot_dir in sorted(root.iterdir()):
        if not bot_dir.is_dir() or not _BOT_ID.fullmatch(bot_dir.name):
            continue
        for source in sorted(bot_dir.iterdir()):
            if (
                not source.is_file()
                or source.is_symlink()
                or source.name.endswith((".meta", ".tmp"))
                or provider_slug(source.name) is None
                or not source.resolve().is_relative_to(resolved_root)
            ):
                continue
            try:
                value = source.read_text(encoding="utf-8").strip()
                meta = source.with_suffix(".meta")
                env_name = ""
                if meta.is_file() and not meta.is_symlink():
                    lines = meta.read_text(encoding="utf-8").splitlines()
                    if len(lines) > 2:
                        env_name = lines[2].strip()
                storage.put(bot_dir.name, source.name, value, env_name=env_name)
                if not storage.confirm_secret(bot_dir.name, source.name, value):
                    raise CredentialStoreError("broker did not confirm migrated credential")
                source.unlink()
                if meta.is_file() and not meta.is_symlink():
                    meta.unlink()
                migrated += 1
            except (OSError, ValueError, CredentialStoreError):
                failed += 1
                log.exception(
                    "credential migration failed bot=%s provider=%s",
                    bot_dir.name,
                    source.name,
                )
        if bot_dir.is_dir() and not any(bot_dir.iterdir()):
            bot_dir.rmdir()
    return MigrationReport(migrated=migrated, failed=failed)


def credential_store_for_settings(settings: Any):
    url = str(settings.credential_broker_url)
    if url.startswith("memory://"):
        if str(settings.agent_runtime) != "scripted":
            raise ValueError("the in-memory credential broker is scripted-test only")
        return InMemoryCredentialStore(Path(settings.agent_data_dir) / "homes")
    token = credential_broker_token(
        str(settings.agent_http_token),
        str(settings.credential_broker_token),
    )
    return CredentialBrokerClient(url, token)


def main() -> int:
    configure_logging()
    explicit = os.environ.get("CREDENTIAL_BROKER_TOKEN", "")
    host_token = os.environ.get("AGENT_HTTP_TOKEN", "")
    if not explicit.strip() and not host_token.strip():
        log.error("credential broker token is not configured")
        return 2
    storage = PrivateCredentialStorage(
        os.environ.get("CREDENTIAL_BROKER_DIR", "/var/lib/artek-buddy/credentials")
    )
    port = int(os.environ.get("CREDENTIAL_BROKER_PORT", "8431"))
    executor_token = os.environ.get("CREDENTIAL_EXECUTOR_TOKEN", "").strip()
    if not executor_token:
        if not host_token.strip():
            log.error("credential executor token is not configured")
            storage.close()
            return 2
        executor_token = derive_credential_executor_token(host_token)
    executor = CredentialExecutorClient(
        os.environ.get("CREDENTIAL_EXECUTOR_URL", "http://127.0.0.1:8432"),
        executor_token,
    )
    server = make_credential_broker_server(
        storage=storage,
        token=credential_broker_token(host_token, explicit),
        executor=executor,
        port=port,
    )
    log.info("credential broker listening on 127.0.0.1:%s", port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        storage.close()
    return 0


def migration_main() -> int:
    configure_logging()
    storage = PrivateCredentialStorage(
        os.environ.get("CREDENTIAL_BROKER_DIR", "/var/lib/artek-buddy/credentials")
    )
    try:
        report = migrate_legacy_credentials(
            os.environ.get("LEGACY_CREDENTIAL_DIR", "/legacy-credentials"),
            storage,
        )
    finally:
        storage.close()
    log.info(
        "credential migration complete migrated=%s failed=%s",
        report.migrated,
        report.failed,
    )
    return 1 if report.failed else 0
