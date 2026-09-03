"""Per-bot GitHub/PyPI tokens on the persistent /data volume.

The computer home under /data/homes is wiped by Reset and rebound on Team ↔
Private. These files live beside that tree, not inside it, and are never
returned after intake.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from artek_buddy.db.shaping import isoformat_utc
from artek_buddy.fs_jail import contained_under

PROVIDERS = ("github", "pypi")
PASTED_CREDENTIAL_DETAIL = (
    "Do not paste GitHub or PyPI tokens in chat. Save them under Settings for this bot."
)

# Classic / OAuth / user-to-server / server-to-server / refresh GitHub tokens.
_GITHUB = re.compile(
    r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}"
    r"|github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9]{59}"
)
# PyPI API tokens are base64 after this issuer prefix.
_PYPI = re.compile(r"pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{16,}")
_ANY = re.compile(_GITHUB.pattern + "|" + _PYPI.pattern)

_BOT_ID = re.compile(r"^bot_[0-9a-f]{16}$")


@dataclass(frozen=True)
class BotCredentialStatus:
    provider: str
    scope: str
    last_four: str
    updated_at: str


def looks_like_pasted_credential(text: str) -> bool:
    return bool(_ANY.search(text or ""))


def pasted_credential_http_error():
    from fastapi import HTTPException

    return HTTPException(status_code=400, detail=PASTED_CREDENTIAL_DETAIL)


def raise_if_pasted_credential(text: str | None) -> None:
    if looks_like_pasted_credential(text or ""):
        raise pasted_credential_http_error()


def _provider_ok(provider: str) -> bool:
    return provider in PROVIDERS


def _secret_matches_provider(provider: str, secret: str) -> bool:
    if provider == "github":
        return bool(_GITHUB.fullmatch(secret))
    if provider == "pypi":
        return bool(_PYPI.fullmatch(secret))
    return False


def last_four(secret: str) -> str:
    value = (secret or "").strip()
    if len(value) < 4:
        return value
    return value[-4:]


class BotCredentialStore:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.root = self.data_dir / "credentials"

    def _bot_dir(self, bot_id: str) -> Path | None:
        if not _BOT_ID.fullmatch(bot_id or ""):
            return None
        return contained_under(self.root, bot_id)

    def _secret_path(self, bot_id: str, provider: str) -> Path | None:
        if not _provider_ok(provider):
            return None
        folder = self._bot_dir(bot_id)
        if folder is None:
            return None
        return contained_under(folder, provider)

    def put(self, bot_id: str, provider: str, secret: str) -> BotCredentialStatus:
        value = (secret or "").strip()
        path = self._secret_path(bot_id, provider)
        if path is None:
            raise ValueError("unknown provider")
        if not value:
            raise ValueError("secret is empty")
        if not _secret_matches_provider(provider, value):
            raise ValueError("secret does not match this provider")
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, stat.S_IRWXU)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(value, encoding="utf-8")
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        tmp.replace(path)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        stamp = isoformat_utc()
        meta = path.with_suffix(".meta")
        meta.write_text(f"{last_four(value)}\n{stamp}\n", encoding="utf-8")
        os.chmod(meta, stat.S_IRUSR | stat.S_IWUSR)
        return BotCredentialStatus(
            provider=provider,
            scope="this_bot",
            last_four=last_four(value),
            updated_at=stamp,
        )

    def read(self, bot_id: str, provider: str) -> str | None:
        path = self._secret_path(bot_id, provider)
        if path is None or not path.is_file():
            return None
        value = path.read_text(encoding="utf-8").strip()
        return value or None

    def status(self, bot_id: str, provider: str) -> BotCredentialStatus | None:
        path = self._secret_path(bot_id, provider)
        if path is None or not path.is_file():
            return None
        meta = path.with_suffix(".meta")
        four = last_four(self.read(bot_id, provider) or "")
        stamp = isoformat_utc()
        if meta.is_file():
            lines = meta.read_text(encoding="utf-8").splitlines()
            if lines:
                four = lines[0].strip() or four
            if len(lines) > 1:
                stamp = lines[1].strip() or stamp
        return BotCredentialStatus(
            provider=provider,
            scope="this_bot",
            last_four=four,
            updated_at=stamp,
        )

    def list(self, bot_id: str) -> list[BotCredentialStatus]:
        rows: list[BotCredentialStatus] = []
        for provider in PROVIDERS:
            row = self.status(bot_id, provider)
            if row is not None:
                rows.append(row)
        return rows

    def forget(self, bot_id: str, provider: str) -> bool:
        path = self._secret_path(bot_id, provider)
        if path is None:
            return False
        existed = path.is_file()
        for item in (path, path.with_suffix(".meta"), path.with_suffix(".tmp")):
            if item.is_file():
                item.unlink()
        folder = path.parent
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
        return existed

    def forget_bot(self, bot_id: str) -> None:
        folder = self._bot_dir(bot_id)
        if folder is None or not folder.is_dir():
            return
        for child in folder.iterdir():
            if child.is_file():
                child.unlink()
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()

    def tool_env(self, bot_id: str) -> dict[str, str]:
        env: dict[str, str] = {}
        github = self.read(bot_id, "github")
        if github:
            env["GH_TOKEN"] = github
            env["GH_PROMPT"] = "never"
        pypi = self.read(bot_id, "pypi")
        if pypi:
            env["UV_PUBLISH_TOKEN"] = pypi
            env["TWINE_USERNAME"] = "__token__"
            env["TWINE_PASSWORD"] = pypi
        return env

    def stored_secrets(self) -> list[str]:
        found: list[str] = []
        if not self.root.is_dir():
            return found
        for bot_dir in self.root.iterdir():
            if not bot_dir.is_dir():
                continue
            for provider in PROVIDERS:
                value = self.read(bot_dir.name, provider)
                if value and len(value) >= 6:
                    found.append(value)
        return found


def stored_secrets(data_dir: str | Path | None = None) -> list[str]:
    root = data_dir or os.environ.get("AGENT_DATA_DIR", "/data")
    try:
        return BotCredentialStore(root).stored_secrets()
    except OSError:
        return []
