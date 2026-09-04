from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from artek_buddy.bot_credentials import (
    PASTED_CREDENTIAL_DETAIL,
    UNNAMED_CREDENTIAL_DETAIL,
    InMemoryCredentialStore,
    apply_chat_credentials,
    last_four,
    looks_like_pasted_credential,
)
from artek_buddy.observe import redact_text

GITHUB_FIXTURE = "ghp_" + ("A" * 36)
PYPI_FIXTURE = "pypi-AgEIcHlwaS5vcmc" + ("B" * 16)
NAMED_FIXTURE = "reg_" + ("Z" * 24)
BOT_A = "bot_" + ("a" * 16)
BOT_B = "bot_" + ("b" * 16)


def _store(tmp_path: Path) -> InMemoryCredentialStore:
    homes = tmp_path / "homes"
    (homes / BOT_A).mkdir(parents=True)
    (homes / BOT_B).mkdir(parents=True)
    return InMemoryCredentialStore(homes)


def _checks_env(store: InMemoryCredentialStore, bot_id: str, env_name: str, secret: str) -> bool:
    digest = hashlib.sha256(secret.encode()).hexdigest()
    body = (
        "import hashlib,os;"
        f"print(hashlib.sha256(os.environ.get({env_name!r}, '').encode()).hexdigest()"
        f" == {digest!r})"
    )
    return store.execute(bot_id, bot_id, f"python -c {json.dumps(body)}").stdout.strip() == "True"


def test_detects_named_and_github_shapes() -> None:
    assert looks_like_pasted_credential(f"token {GITHUB_FIXTURE} please")
    assert looks_like_pasted_credential(PYPI_FIXTURE)
    assert looks_like_pasted_credential(f"REGISTRY_TOKEN={NAMED_FIXTURE}")
    assert not looks_like_pasted_credential("please push to GitHub")
    assert not looks_like_pasted_credential("please e2e-worker-progress")
    assert not looks_like_pasted_credential("e2e-consent-auto-read")
    assert not looks_like_pasted_credential("e2e-consent-read-escape")
    assert PASTED_CREDENTIAL_DETAIL
    assert UNNAMED_CREDENTIAL_DETAIL


def test_chat_named_token_is_stored_and_stripped(tmp_path: Path) -> None:
    store = _store(tmp_path)
    text = f"use REGISTRY_TOKEN={NAMED_FIXTURE} to publish"
    visible = apply_chat_credentials(store, BOT_A, text)
    assert NAMED_FIXTURE not in visible
    assert "use" in visible
    assert last_four(NAMED_FIXTURE) in visible
    assert store.list_for_bot(BOT_A)[0].provider == "registry-token"
    assert _checks_env(store, BOT_A, "REGISTRY_TOKEN", NAMED_FIXTURE)
    assert store.list_for_bot(BOT_B) == []


def test_chat_github_shape_is_stored_not_left_in_text(tmp_path: Path) -> None:
    store = _store(tmp_path)
    visible = apply_chat_credentials(store, BOT_A, f"use {GITHUB_FIXTURE}")
    assert GITHUB_FIXTURE not in visible
    assert "use" in visible
    assert last_four(GITHUB_FIXTURE) in visible
    assert _checks_env(store, BOT_A, "GH_TOKEN", GITHUB_FIXTURE)


def test_scripted_e2e_prompt_is_not_intake(tmp_path: Path) -> None:
    store = _store(tmp_path)
    text = "e2e-consent-auto-read"
    assert apply_chat_credentials(store, BOT_A, text) == text
    assert store.list_for_bot(BOT_A) == []


def test_unlabeled_blob_is_not_stored(tmp_path: Path) -> None:
    store = _store(tmp_path)
    blob = "AbCdEfGhIjKlMnOpQrStUvWxYz012345"
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        apply_chat_credentials(store, BOT_A, blob)
    assert caught.value.status_code == 400
    assert caught.value.detail == UNNAMED_CREDENTIAL_DETAIL
    assert store.list_for_bot(BOT_A) == []


def test_store_roundtrip_and_isolation(tmp_path: Path) -> None:
    vault = _store(tmp_path)
    github = vault.put(BOT_A, "github", GITHUB_FIXTURE)
    pypi = vault.put(BOT_A, "pypi", PYPI_FIXTURE)
    named = vault.put(BOT_A, "registry-token", NAMED_FIXTURE, env_name="REGISTRY_TOKEN")
    assert github.last_four == last_four(GITHUB_FIXTURE)
    assert pypi.last_four == last_four(PYPI_FIXTURE)
    assert named.last_four == last_four(NAMED_FIXTURE)
    assert github.scope == "this_bot"
    assert {row.provider for row in vault.list_for_bot(BOT_A)} == {
        "github",
        "pypi",
        "registry-token",
    }
    assert vault.list_for_bot(BOT_B) == []
    assert _checks_env(vault, BOT_A, "GH_TOKEN", GITHUB_FIXTURE)
    assert _checks_env(vault, BOT_A, "UV_PUBLISH_TOKEN", PYPI_FIXTURE)
    assert _checks_env(vault, BOT_A, "REGISTRY_TOKEN", NAMED_FIXTURE)
    assert not hasattr(vault, "read")


def test_replace_and_forget_drop_old_value(tmp_path: Path) -> None:
    vault = _store(tmp_path)
    vault.put(BOT_A, "github", GITHUB_FIXTURE)
    replacement = "ghp_" + ("C" * 36)
    vault.put(BOT_A, "github", replacement)
    assert vault.list_for_bot(BOT_A)[0].last_four == "CCCC"
    assert _checks_env(vault, BOT_A, "GH_TOKEN", replacement)
    assert vault.forget(BOT_A, "github") is True
    assert vault.list_for_bot(BOT_A) == []
    vault.put(BOT_A, "pypi", PYPI_FIXTURE)
    vault.forget_bot(BOT_A)
    assert vault.list_for_bot(BOT_A) == []


def test_homes_path_is_not_the_store(tmp_path: Path) -> None:
    vault = _store(tmp_path)
    vault.put(BOT_A, "github", GITHUB_FIXTURE)
    homes = tmp_path / "homes" / "team-ws"
    homes.mkdir(parents=True)
    assert not (tmp_path / "credentials").exists()
    assert all(
        GITHUB_FIXTURE not in path.read_text(errors="ignore")
        for path in tmp_path.rglob("*")
        if path.is_file()
    )


def test_observe_redacts_explicit_broker_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CREDENTIAL_BROKER_TOKEN", GITHUB_FIXTURE)
    text = redact_text(f"Authorization: Bearer {GITHUB_FIXTURE}")
    assert GITHUB_FIXTURE not in text
    assert "[redacted]" in text


def test_rejects_invalid_slug(tmp_path: Path) -> None:
    vault = _store(tmp_path)
    with pytest.raises(ValueError, match="unknown provider"):
        vault.put(BOT_A, "../etc", NAMED_FIXTURE)
    with pytest.raises(ValueError, match="secret is empty"):
        vault.put(BOT_A, "registry-token", "   ")
