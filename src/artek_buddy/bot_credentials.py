"""Per-bot authorization tokens on the persistent /data volume.

The computer home under /data/homes is wiped by Reset and rebound on Team ↔
Private. These files live beside that tree, not inside it, and are never
returned after intake. Chat is intake: a pasted secret is stored here and
stripped from the thread.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from artek_buddy.db.shaping import isoformat_utc
from artek_buddy.fs_jail import contained_under

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


@dataclass(frozen=True)
class BotCredentialStatus:
    provider: str
    scope: str
    last_four: str
    updated_at: str
    env_name: str = ""


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


def apply_chat_credentials(data_dir: str | Path, bot_id: str, text: str) -> str:
    raw = text or ""
    found = find_chat_credentials(raw)
    if not found and _is_secret_blob(raw.strip()):
        raise unnamed_credential_http_error()
    if not found:
        return raw
    vault = BotCredentialStore(data_dir)
    try:
        for item in found:
            vault.put(bot_id, item.provider, item.secret, env_name=item.env_name)
    except ValueError as err:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(err)) from err
    return redact_found(raw, found)


def _write_private(path: Path, body: str) -> None:
    """Write a 0600 host-local file. Plaintext is the THREAT-MODEL.md residual."""
    # codeql[py/clear-text-storage-sensitive-data]
    path.write_text(body, encoding="utf-8")  # lgtm[py/clear-text-storage-sensitive-data]


class BotCredentialStore:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.root = self.data_dir / "credentials"

    def _bot_dir(self, bot_id: str) -> Path | None:
        if not _BOT_ID.fullmatch(bot_id or ""):
            return None
        return contained_under(self.root, bot_id)  # lgtm[py/path-injection]

    def _secret_path(self, bot_id: str, provider: str) -> Path | None:
        slug = provider_slug(provider)
        if slug is None:
            return None
        folder = self._bot_dir(bot_id)
        if folder is None:
            return None
        return contained_under(folder, slug)  # lgtm[py/path-injection]

    def put(
        self,
        bot_id: str,
        provider: str,
        secret: str,
        env_name: str = "",
    ) -> BotCredentialStatus:
        value = (secret or "").strip()
        slug = provider_slug(provider)
        path = self._secret_path(bot_id, provider)
        if path is None or slug is None:
            raise ValueError("unknown provider")
        if not value:
            raise ValueError("secret is empty")
        if len(value) > 8000:
            raise ValueError("secret is too long")
        env = (env_name or "").strip().upper() or _env_from_slug(slug)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", env):
            env = _env_from_slug(slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, stat.S_IRWXU)
        tmp = path.with_suffix(".tmp")
        _write_private(tmp, value)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        tmp.replace(path)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        stamp = isoformat_utc()
        meta = path.with_suffix(".meta")
        _write_private(meta, f"{last_four(value)}\n{stamp}\n{env}\n")
        os.chmod(meta, stat.S_IRUSR | stat.S_IWUSR)
        return BotCredentialStatus(
            provider=slug,
            scope="this_bot",
            last_four=last_four(value),
            updated_at=stamp,
            env_name=env,
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
        slug = provider_slug(provider) or provider
        meta = path.with_suffix(".meta")
        four = last_four(self.read(bot_id, provider) or "")
        stamp = isoformat_utc()
        env = _env_from_slug(slug)
        if meta.is_file():
            lines = meta.read_text(encoding="utf-8").splitlines()
            if lines:
                four = lines[0].strip() or four
            if len(lines) > 1:
                stamp = lines[1].strip() or stamp
            if len(lines) > 2 and lines[2].strip():
                env = lines[2].strip()
        return BotCredentialStatus(
            provider=slug,
            scope="this_bot",
            last_four=four,
            updated_at=stamp,
            env_name=env,
        )

    def list_for_bot(self, bot_id: str) -> list[BotCredentialStatus]:
        folder = self._bot_dir(bot_id)
        names: list[str] = []
        if folder is not None and folder.is_dir():
            for child in folder.iterdir():
                if not child.is_file():
                    continue
                if child.name.endswith((".meta", ".tmp")):
                    continue
                if provider_slug(child.name) is None:
                    continue
                names.append(child.name)
        order = {"github": 0, "pypi": 1}
        names.sort(key=lambda name: (order.get(name, 50), name))
        rows: list[BotCredentialStatus] = []
        for name in names:
            row = self.status(bot_id, name)
            if row is not None:
                rows.append(row)
        return rows

    def forget(self, bot_id: str, provider: str) -> bool:
        path = self._secret_path(bot_id, provider)
        if path is None:
            return False
        existed = path.is_file()
        for item in (
            path,
            path.with_suffix(".meta"),
            path.with_suffix(".tmp"),
        ):
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
        for row in self.list_for_bot(bot_id):
            secret = self.read(bot_id, row.provider)
            if not secret:
                continue
            name = row.env_name or _env_from_slug(row.provider)
            env[name] = secret
            if row.provider == "github":
                env["GH_TOKEN"] = secret
                env["GH_PROMPT"] = "never"
            if row.provider == "pypi":
                env["UV_PUBLISH_TOKEN"] = secret
                env["TWINE_USERNAME"] = "__token__"
                env["TWINE_PASSWORD"] = secret
        return env

    def stored_secrets(self) -> list[str]:
        found: list[str] = []
        if not self.root.is_dir():
            return found
        for bot_dir in self.root.iterdir():
            if not bot_dir.is_dir():
                continue
            for row in self.list_for_bot(bot_dir.name):
                value = self.read(bot_dir.name, row.provider)
                if value and len(value) >= 6:
                    found.append(value)
        return found


def stored_secrets(data_dir: str | Path | None = None) -> list[str]:
    root = data_dir or os.environ.get("AGENT_DATA_DIR", "/data")
    try:
        return BotCredentialStore(root).stored_secrets()
    except OSError:
        return []
