"""Credential intake and the metadata-only broker client contract."""

from __future__ import annotations

import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from artek_buddy.db.shaping import isoformat_utc

PASTED_CREDENTIAL_DETAIL = "Do not paste tokens here. Save them under Settings for this bot."
UNNAMED_CREDENTIAL_DETAIL = "Name this token under Settings for this bot, then Store."

_PROVIDER = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_BOT_ID = re.compile(r"^bot_[0-9a-f]{16}$")
_CRED_ENV = re.compile(
    r"(TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|APIKEY|API_KEY|_KEY$|^KEY_|_PAT$|_AUTH$)",
    re.IGNORECASE,
)
_ENV_ASSIGN = re.compile(
    r"(?:^|(?<=\s))(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]{1,63})"
    r"\s*=\s*(?P<q>['\"]?)(?P<secret>[^\s'\"]{12,8000})(?P=q)"
)
_BLOB = re.compile(r"^[A-Za-z0-9_\-.=+/]{20,8000}$")

# Classic / OAuth / user-to-server / server-to-server / refresh GitHub tokens.
_GITHUB = re.compile(
    r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}"
    r"|github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9]{59}"
)
_PYPI = re.compile(r"pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{16,}")
_NPM = re.compile(r"npm_[A-Za-z0-9]{36,}")
_GITLAB = re.compile(r"glpat-[A-Za-z0-9_-]{20,}")
_HF = re.compile(r"hf_[A-Za-z0-9]{20,}")

_SHAPES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (_GITHUB, "github", "GH_TOKEN"),
    (_PYPI, "pypi", "UV_PUBLISH_TOKEN"),
    (_NPM, "npm", "NPM_TOKEN"),
    (_GITLAB, "gitlab", "GITLAB_TOKEN"),
    (_HF, "huggingface", "HF_TOKEN"),
)

_ENV_PROVIDER = {
    "GH_TOKEN": "github",
    "GITHUB_TOKEN": "github",
    "GITHUB_PAT": "github",
    "UV_PUBLISH_TOKEN": "pypi",
    "TWINE_PASSWORD": "pypi",
    "PYPI_TOKEN": "pypi",
    "NPM_TOKEN": "npm",
    "GITLAB_TOKEN": "gitlab",
    "GL_TOKEN": "gitlab",
    "HF_TOKEN": "huggingface",
    "HUGGING_FACE_HUB_TOKEN": "huggingface",
}

_ALIASES = {
    "gh-token": "github",
    "github-token": "github",
    "github-pat": "github",
    "uv-publish-token": "pypi",
    "twine-password": "pypi",
    "pypi-token": "pypi",
    "npm-token": "npm",
    "gitlab-token": "gitlab",
    "gl-token": "gitlab",
    "hf-token": "huggingface",
    "hugging-face-hub-token": "huggingface",
}

_LABELS = {
    "github": "GitHub",
    "pypi": "PyPI",
    "npm": "npm",
    "gitlab": "GitLab",
    "huggingface": "Hugging Face",
}

_RESERVED_ENV_NAMES = {
    "BASH_ENV",
    "BASHOPTS",
    "CDPATH",
    "ENV",
    "GIT_TERMINAL_PROMPT",
    "HOME",
    "IFS",
    "LANG",
    "LC_ALL",
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "PATH",
    "PROMPT_COMMAND",
    "PS4",
    "PYTHONHOME",
    "PYTHONPATH",
    "SHELL",
    "SHELLOPTS",
}


@dataclass(frozen=True)
class BotCredentialStatus:
    provider: str
    scope: str
    last_four: str
    updated_at: str
    env_name: str = ""


@dataclass(frozen=True)
class CredentialExecutionResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    truncated: bool = False
    error: str = ""


class CredentialStoreError(RuntimeError):
    """The isolated credential service rejected or could not perform an operation."""


class CredentialStoreUnavailable(CredentialStoreError):
    """The isolated credential service is unavailable."""


class BotCredentialStore(Protocol):
    def put(
        self,
        bot_id: str,
        provider: str,
        secret: str,
        env_name: str = "",
    ) -> BotCredentialStatus: ...

    def list_for_bot(self, bot_id: str) -> list[BotCredentialStatus]: ...

    def forget(self, bot_id: str, provider: str) -> bool: ...

    def forget_bot(self, bot_id: str) -> None: ...

    def execute(
        self,
        bot_id: str,
        home_key: str,
        command: str,
        *,
        cwd: str = ".",
        timeout_seconds: float = 30,
    ) -> CredentialExecutionResult: ...


@dataclass(frozen=True)
class _Found:
    provider: str
    secret: str
    env_name: str
    start: int
    end: int


def provider_slug(raw: str) -> str | None:
    text = (raw or "").strip().lower().replace("_", "-")
    text = _ALIASES.get(text, text)
    if not _PROVIDER.fullmatch(text):
        return None
    return text


def provider_label(provider: str) -> str:
    slug = provider_slug(provider) or (provider or "").strip()
    return _LABELS.get(slug, slug.replace("-", " "))


def last_four(secret: str) -> str:
    value = (secret or "").strip()
    if len(value) < 4:
        return value
    return value[-4:]


def _env_from_slug(slug: str) -> str:
    if slug == "github":
        return "GH_TOKEN"
    if slug == "pypi":
        return "UV_PUBLISH_TOKEN"
    return slug.upper().replace("-", "_")


def normalized_credential_env(provider: str, env_name: str = "") -> str:
    env = (env_name or "").strip().upper() or _env_from_slug(provider)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", env):
        env = _env_from_slug(provider)
    if env in _RESERVED_ENV_NAMES:
        raise ValueError("credential environment name is reserved")
    return env


def _is_cred_env(name: str) -> bool:
    upper = (name or "").upper()
    if upper in _ENV_PROVIDER:
        return True
    return bool(_CRED_ENV.search(upper))


def _is_secret_blob(text: str) -> bool:
    value = (text or "").strip()
    if not _BLOB.fullmatch(value):
        return False
    lowered = value.lower()
    if lowered.startswith("please") or lowered.startswith("e2e-"):
        return False
    if "://" in value:
        return False
    hex_only = re.fullmatch(r"[0-9a-fA-F]{20,40}", value)
    if hex_only:
        return False
    has_upper = any(ch.isupper() for ch in value)
    has_lower = any(ch.islower() for ch in value)
    has_digit = any(ch.isdigit() for ch in value)
    return has_upper and has_lower and has_digit


def find_chat_credentials(text: str) -> list[_Found]:
    raw = text or ""
    found: list[_Found] = []
    covered: list[tuple[int, int]] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(start < stop and end > begin for begin, stop in covered)

    def _add(item: _Found) -> None:
        if _overlaps(item.start, item.end):
            return
        found.append(item)
        covered.append((item.start, item.end))

    for match in _ENV_ASSIGN.finditer(raw):
        name = match.group("name")
        secret = match.group("secret")
        if not _is_cred_env(name):
            continue
        slug = provider_slug(name)
        if slug is None:
            continue
        _add(
            _Found(
                provider=slug,
                secret=secret,
                env_name=name.upper(),
                start=match.start(),
                end=match.end(),
            )
        )
    for pattern, slug, env_name in _SHAPES:
        for match in pattern.finditer(raw):
            _add(
                _Found(
                    provider=slug,
                    secret=match.group(0),
                    env_name=env_name,
                    start=match.start(),
                    end=match.end(),
                )
            )
    return found


def looks_like_pasted_credential(text: str) -> bool:
    raw = text or ""
    if find_chat_credentials(raw):
        return True
    return _is_secret_blob(raw.strip())


def pasted_credential_http_error():
    from fastapi import HTTPException

    return HTTPException(status_code=400, detail=PASTED_CREDENTIAL_DETAIL)


def unnamed_credential_http_error():
    from fastapi import HTTPException

    return HTTPException(status_code=400, detail=UNNAMED_CREDENTIAL_DETAIL)


def raise_if_pasted_credential(text: str | None) -> None:
    if looks_like_pasted_credential(text or ""):
        raise pasted_credential_http_error()


def _mask(secret: str) -> str:
    return f"••••{last_four(secret)}"


def _saved_summary(found: list[_Found]) -> str:
    bits = ", ".join(f"{provider_label(item.provider)} · {_mask(item.secret)}" for item in found)
    if len(found) == 1:
        return f"Saved a token for this bot ({bits})."
    return f"Saved tokens for this bot ({bits})."


def redact_found(text: str, found: list[_Found]) -> str:
    out = text or ""
    for item in sorted(found, key=lambda row: row.start, reverse=True):
        out = out[: item.start] + _mask(item.secret) + out[item.end :]
    leftover = out
    for item in found:
        leftover = leftover.replace(_mask(item.secret), "")
    if not leftover.strip():
        return _saved_summary(found)
    return out


def apply_chat_credentials(store: BotCredentialStore, bot_id: str, text: str) -> str:
    raw = text or ""
    found = find_chat_credentials(raw)
    if not found and _is_secret_blob(raw.strip()):
        raise unnamed_credential_http_error()
    if not found:
        return raw
    try:
        for item in found:
            store.put(bot_id, item.provider, item.secret, env_name=item.env_name)
    except ValueError as err:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(err)) from err
    except CredentialStoreError as err:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="credential broker unavailable") from err
    return redact_found(raw, found)


def credential_env(rows: Sequence[tuple[BotCredentialStatus, str]]) -> dict[str, str]:
    env: dict[str, str] = {}
    for row, secret in rows:
        name = row.env_name or _env_from_slug(row.provider)
        env[name] = secret
        if row.provider == "github":
            env["GH_TOKEN"] = secret
            env["GITHUB_TOKEN"] = secret
            env["GH_PROMPT"] = "never"
        if row.provider == "pypi":
            env["UV_PUBLISH_TOKEN"] = secret
            env["PYPI_TOKEN"] = secret
            env["TWINE_USERNAME"] = "__token__"
            env["TWINE_PASSWORD"] = secret
    return env


class InMemoryCredentialStore:
    """Explicit test broker. Production settings default to the HTTP client."""

    def __init__(self, homes_root: str | Path) -> None:
        self.homes_root = Path(homes_root)
        self._rows: dict[tuple[str, str], tuple[BotCredentialStatus, str]] = {}
        self._lock = threading.RLock()

    def put(
        self,
        bot_id: str,
        provider: str,
        secret: str,
        env_name: str = "",
    ) -> BotCredentialStatus:
        value = (secret or "").strip()
        slug = provider_slug(provider)
        if not _BOT_ID.fullmatch(bot_id or ""):
            raise ValueError("invalid bot id")
        if slug is None:
            raise ValueError("unknown provider")
        if not value:
            raise ValueError("secret is empty")
        if len(value) > 8000:
            raise ValueError("secret is too long")
        env = normalized_credential_env(slug, env_name)
        row = BotCredentialStatus(
            provider=slug,
            scope="this_bot",
            last_four=last_four(value),
            updated_at=isoformat_utc(),
            env_name=env,
        )
        with self._lock:
            self._rows[(bot_id, slug)] = (row, value)
        return row

    def list_for_bot(self, bot_id: str) -> list[BotCredentialStatus]:
        with self._lock:
            rows = [
                row
                for (current, _provider), (row, _secret) in self._rows.items()
                if current == bot_id
            ]
        order = {"github": 0, "pypi": 1}
        return sorted(rows, key=lambda row: (order.get(row.provider, 50), row.provider))

    def forget(self, bot_id: str, provider: str) -> bool:
        slug = provider_slug(provider)
        if slug is None:
            return False
        with self._lock:
            return self._rows.pop((bot_id, slug), None) is not None

    def forget_bot(self, bot_id: str) -> None:
        with self._lock:
            for key in [key for key in self._rows if key[0] == bot_id]:
                self._rows.pop(key, None)

    def execute(
        self,
        bot_id: str,
        home_key: str,
        command: str,
        *,
        cwd: str = ".",
        timeout_seconds: float = 30,
    ) -> CredentialExecutionResult:
        from artek_buddy.credential_executor import execute_credential_command

        with self._lock:
            bot_rows = [
                item for (current, _provider), item in self._rows.items() if current == bot_id
            ]
            secrets = [secret for _row, secret in self._rows.values()]
        return execute_credential_command(
            homes_root=self.homes_root,
            bot_id=bot_id,
            home_key=home_key,
            command=command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            injected_env=credential_env(bot_rows),
            redacted_secrets=secrets,
        )
