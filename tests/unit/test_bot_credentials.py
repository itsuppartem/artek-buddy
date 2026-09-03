from __future__ import annotations

from pathlib import Path

import pytest

from artek_buddy.bot_credentials import (
    PASTED_CREDENTIAL_DETAIL,
    UNNAMED_CREDENTIAL_DETAIL,
    BotCredentialStore,
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


def test_detects_named_and_github_shapes() -> None:
    assert looks_like_pasted_credential(f"token {GITHUB_FIXTURE} please")
    assert looks_like_pasted_credential(PYPI_FIXTURE)
    assert looks_like_pasted_credential(f"REGISTRY_TOKEN={NAMED_FIXTURE}")
    assert not looks_like_pasted_credential("please push to GitHub")
    assert not looks_like_pasted_credential("please e2e-worker-progress")
    assert PASTED_CREDENTIAL_DETAIL
    assert UNNAMED_CREDENTIAL_DETAIL


def test_chat_named_token_is_stored_and_stripped(tmp_path: Path) -> None:
    text = f"use REGISTRY_TOKEN={NAMED_FIXTURE} to publish"
    visible = apply_chat_credentials(tmp_path, BOT_A, text)
    assert NAMED_FIXTURE not in visible
    assert "use" in visible
    assert last_four(NAMED_FIXTURE) in visible
    vault = BotCredentialStore(tmp_path)
    assert vault.read(BOT_A, "registry-token") == NAMED_FIXTURE
    env = vault.tool_env(BOT_A)
    assert env["REGISTRY_TOKEN"] == NAMED_FIXTURE
    assert vault.read(BOT_B, "registry-token") is None


def test_chat_github_shape_is_stored_not_left_in_text(tmp_path: Path) -> None:
    visible = apply_chat_credentials(tmp_path, BOT_A, f"use {GITHUB_FIXTURE}")
    assert GITHUB_FIXTURE not in visible
    assert "use" in visible
    assert last_four(GITHUB_FIXTURE) in visible
    assert BotCredentialStore(tmp_path).read(BOT_A, "github") == GITHUB_FIXTURE


def test_unlabeled_blob_is_not_stored(tmp_path: Path) -> None:
    blob = "AbCdEfGhIjKlMnOpQrStUvWxYz012345"
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        apply_chat_credentials(tmp_path, BOT_A, blob)
    assert caught.value.status_code == 400
    assert caught.value.detail == UNNAMED_CREDENTIAL_DETAIL
    assert BotCredentialStore(tmp_path).list_for_bot(BOT_A) == []


def test_store_roundtrip_and_isolation(tmp_path: Path) -> None:
    vault = BotCredentialStore(tmp_path)
    github = vault.put(BOT_A, "github", GITHUB_FIXTURE)
    pypi = vault.put(BOT_A, "pypi", PYPI_FIXTURE)
    named = vault.put(BOT_A, "registry-token", NAMED_FIXTURE, env_name="REGISTRY_TOKEN")
    assert github.last_four == last_four(GITHUB_FIXTURE)
    assert pypi.last_four == last_four(PYPI_FIXTURE)
    assert named.last_four == last_four(NAMED_FIXTURE)
    assert github.scope == "this_bot"
    other = BotCredentialStore(tmp_path)
    assert other.read(BOT_A, "github") == GITHUB_FIXTURE
    assert other.read(BOT_A, "pypi") == PYPI_FIXTURE
    assert other.read(BOT_A, "registry-token") == NAMED_FIXTURE
    assert other.read(BOT_B, "github") is None
    assert other.list_for_bot(BOT_B) == []
    env_a = other.tool_env(BOT_A)
    env_b = other.tool_env(BOT_B)
    assert env_a["GH_TOKEN"] == GITHUB_FIXTURE
    assert env_a["UV_PUBLISH_TOKEN"] == PYPI_FIXTURE
    assert env_a["REGISTRY_TOKEN"] == NAMED_FIXTURE
    assert "https://" not in " ".join(env_a.values())
    assert env_b == {}


def test_replace_and_forget_drop_old_value(tmp_path: Path) -> None:
    vault = BotCredentialStore(tmp_path)
    vault.put(BOT_A, "github", GITHUB_FIXTURE)
    replacement = "ghp_" + ("C" * 36)
    vault.put(BOT_A, "github", replacement)
    assert vault.read(BOT_A, "github") == replacement
    assert GITHUB_FIXTURE not in vault.read(BOT_A, "github")
    assert vault.forget(BOT_A, "github") is True
    assert vault.read(BOT_A, "github") is None
    vault.put(BOT_A, "pypi", PYPI_FIXTURE)
    vault.forget_bot(BOT_A)
    assert vault.read(BOT_A, "pypi") is None
    cred_root = tmp_path / "credentials" / BOT_A
    assert not cred_root.exists()


def test_homes_path_is_not_the_store(tmp_path: Path) -> None:
    vault = BotCredentialStore(tmp_path)
    vault.put(BOT_A, "github", GITHUB_FIXTURE)
    homes = tmp_path / "homes" / "team-ws"
    homes.mkdir(parents=True)
    (homes / "stolen").write_text(GITHUB_FIXTURE, encoding="utf-8")
    for path in (tmp_path / "credentials").rglob("*"):
        if path.is_file() and "homes" in path.parts:
            pytest.fail("credential file leaked into homes")
    assert (tmp_path / "credentials" / BOT_A / "github").is_file()
    assert not str(tmp_path / "credentials").startswith(str(homes))


def test_observe_redacts_stored_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    BotCredentialStore(tmp_path).put(BOT_A, "github", GITHUB_FIXTURE)
    text = redact_text(f"export GH_TOKEN={GITHUB_FIXTURE}")
    assert GITHUB_FIXTURE not in text
    assert "[redacted]" in text


def test_rejects_invalid_slug(tmp_path: Path) -> None:
    vault = BotCredentialStore(tmp_path)
    with pytest.raises(ValueError, match="unknown provider"):
        vault.put(BOT_A, "../etc", NAMED_FIXTURE)
    with pytest.raises(ValueError, match="secret is empty"):
        vault.put(BOT_A, "registry-token", "   ")
