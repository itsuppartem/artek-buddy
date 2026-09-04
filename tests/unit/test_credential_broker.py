from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from artek_buddy.auth import (
    derive_credential_broker_token,
    derive_credential_executor_token,
)
from artek_buddy.bot_credentials import CredentialExecutionResult, InMemoryCredentialStore
from artek_buddy.credential_broker import (
    CredentialBrokerClient,
    PrivateCredentialStorage,
    credential_store_for_settings,
    make_credential_broker_server,
    migrate_legacy_credentials,
)
from artek_buddy.credential_executor import (
    CredentialExecutorClient,
)

HOST_TOKEN = "ci-host-token-aabbccddeeff001122334455"
BROKER_TOKEN = derive_credential_broker_token(HOST_TOKEN)
EXECUTOR_TOKEN = derive_credential_executor_token(HOST_TOKEN)
GITHUB_FIXTURE = "ghp_" + ("A" * 36)
GITHUB_REPLACEMENT = "ghp_" + ("C" * 36)
PYPI_FIXTURE = "pypi-AgEIcHlwaS5vcmc" + ("B" * 16)
BOT_A = "bot_" + ("a" * 16)
BOT_B = "bot_" + ("b" * 16)
HOME_A = BOT_A
HOME_B = BOT_B


@contextmanager
def _running_broker(tmp_path: Path) -> Iterator[tuple[CredentialBrokerClient, object]]:
    homes = tmp_path / "homes"
    (homes / HOME_A).mkdir(parents=True)
    (homes / HOME_B).mkdir(parents=True)
    storage = PrivateCredentialStorage(tmp_path / "broker")

    class Executor:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def execute(self, **kwargs):
            self.calls.append(kwargs)
            env = kwargs["injected_env"]
            command = kwargs["command"]
            relative = Path(kwargs["cwd"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("cwd must stay under this bot home")
            if "sleep(2)" in command:
                return CredentialExecutionResult(
                    ok=False,
                    exit_code=124,
                    stdout="",
                    stderr="",
                    timed_out=True,
                    error="command timed out",
                )
            if "'x' * 100000" in command:
                return CredentialExecutionResult(
                    ok=True,
                    exit_code=0,
                    stdout="x" * (64 * 1024) + "\n[output truncated]",
                    stderr="",
                    truncated=True,
                )
            if "Path.cwd().name" in command:
                return CredentialExecutionResult(
                    ok=True,
                    exit_code=0,
                    stdout=f"{Path(kwargs['cwd']).name}\n",
                    stderr="",
                )
            exposed = env.get("GH_TOKEN", "")
            return CredentialExecutionResult(
                ok=True,
                exit_code=0,
                stdout=f"fixture-seen=true\n{exposed}",
                stderr=exposed,
            )

    executor = Executor()
    server = make_credential_broker_server(
        storage=storage,
        token=BROKER_TOKEN,
        executor=executor,
        port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    assert host == "127.0.0.1"
    try:
        yield CredentialBrokerClient(f"http://127.0.0.1:{port}", BROKER_TOKEN), server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        storage.close()


def _python_check(expression: str, *, expose: str = "") -> str:
    statements = [
        "import os,sys",
        f"print('fixture-seen=' + str(bool({expression})).lower())",
    ]
    if expose:
        statements.extend(
            [
                f"print(os.environ.get({expose!r}, 'missing'))",
                f"print(os.environ.get({expose!r}, 'missing'), file=sys.stderr)",
            ]
        )
    body = ";".join(statements)
    return f"python -c {json.dumps(body)}"


def test_broker_requires_derived_token_and_rejects_raw_host_bearer(tmp_path: Path) -> None:
    with _running_broker(tmp_path) as (client, server):
        host, port = server.server_address
        url = f"http://{host}:{port}/v1/credentials/list"
        for token in ("", HOST_TOKEN, "wrong-broker-token"):
            request = urllib.request.Request(
                url,
                data=json.dumps({"bot_id": BOT_A}).encode(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with pytest.raises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=1)
            assert caught.value.code == 403
        assert client.list_for_bot(BOT_A) == []


def test_put_list_delete_and_delete_bot_return_metadata_only(tmp_path: Path) -> None:
    with _running_broker(tmp_path) as (client, _server):
        github = client.put(BOT_A, "github", GITHUB_FIXTURE)
        pypi = client.put(BOT_A, "pypi", PYPI_FIXTURE)
        listed = client.list_for_bot(BOT_A)
        assert github.last_four == "AAAA"
        assert pypi.last_four == "BBBB"
        assert {row.provider for row in listed} == {"github", "pypi"}
        assert GITHUB_FIXTURE not in repr(listed)
        assert PYPI_FIXTURE not in repr(listed)
        assert client.list_for_bot(BOT_B) == []
        assert client.forget(BOT_A, "github") is True
        assert [row.provider for row in client.list_for_bot(BOT_A)] == ["pypi"]
        client.forget_bot(BOT_A)
        assert client.list_for_bot(BOT_A) == []


def test_execution_injects_aliases_redacts_both_streams_and_isolates_bots(
    tmp_path: Path,
) -> None:
    github_hash = hashlib.sha256(GITHUB_FIXTURE.encode()).hexdigest()
    pypi_hash = hashlib.sha256(PYPI_FIXTURE.encode()).hexdigest()
    with _running_broker(tmp_path) as (client, server):
        client.put(BOT_A, "github", GITHUB_FIXTURE)
        client.put(BOT_A, "pypi", PYPI_FIXTURE)
        result = client.execute(
            BOT_A,
            HOME_A,
            _python_check(
                (
                    f"__import__('hashlib').sha256(os.environ['GH_TOKEN'].encode()).hexdigest() == "
                    f"{github_hash!r} and os.environ['GITHUB_TOKEN'] == os.environ['GH_TOKEN'] and "
                    f"__import__('hashlib').sha256(os.environ['UV_PUBLISH_TOKEN'].encode()).hexdigest() == "
                    f"{pypi_hash!r} and os.environ['TWINE_PASSWORD'] == "
                    "os.environ['UV_PUBLISH_TOKEN'] and os.environ['TWINE_USERNAME'] == '__token__'"
                ),
                expose="GH_TOKEN",
            ),
        )
        packed = json.dumps(asdict(result))
        assert result.ok is True
        assert "fixture-seen=true" in result.stdout
        assert "[redacted]" in result.stdout
        assert "[redacted]" in result.stderr
        assert GITHUB_FIXTURE not in packed
        assert PYPI_FIXTURE not in packed

        isolated = client.execute(
            BOT_B,
            HOME_B,
            _python_check("'GH_TOKEN' not in os.environ and 'UV_PUBLISH_TOKEN' not in os.environ"),
        )
        assert isolated.ok is True
        assert "fixture-seen=true" in isolated.stdout
        assert "AAAA" not in json.dumps(asdict(isolated))
        calls = server.executor.calls
        assert calls[0]["injected_env"]["GH_TOKEN"] == GITHUB_FIXTURE
        assert calls[0]["injected_env"]["UV_PUBLISH_TOKEN"] == PYPI_FIXTURE
        assert "GH_TOKEN" not in calls[1]["injected_env"]
        assert "UV_PUBLISH_TOKEN" not in calls[1]["injected_env"]


def test_replace_forget_named_env_and_no_process_environment_mutation(tmp_path: Path) -> None:
    original_environment = dict(os.environ)
    replacement_hash = hashlib.sha256(GITHUB_REPLACEMENT.encode()).hexdigest()
    named = "reg_" + ("Z" * 24)
    with _running_broker(tmp_path) as (client, server):
        client.put(BOT_A, "github", GITHUB_FIXTURE)
        client.put(BOT_A, "github", GITHUB_REPLACEMENT)
        client.put(BOT_A, "registry-token", named, env_name="REGISTRY_TOKEN")
        replaced = client.execute(
            BOT_A,
            HOME_A,
            _python_check(
                f"__import__('hashlib').sha256(os.environ['GH_TOKEN'].encode()).hexdigest() == "
                f"{replacement_hash!r} and os.environ['REGISTRY_TOKEN'].endswith('ZZZZ')"
            ),
        )
        assert "fixture-seen=true" in replaced.stdout
        client.forget(BOT_A, "github")
        forgotten = client.execute(
            BOT_A,
            HOME_A,
            _python_check("'GH_TOKEN' not in os.environ and 'REGISTRY_TOKEN' in os.environ"),
        )
        assert "fixture-seen=true" in forgotten.stdout
        assert server.executor.calls[0]["injected_env"]["GH_TOKEN"] == GITHUB_REPLACEMENT
        assert "GH_TOKEN" not in server.executor.calls[1]["injected_env"]
    assert dict(os.environ) == original_environment
    assert GITHUB_FIXTURE not in os.environ.values()
    assert GITHUB_REPLACEMENT not in os.environ.values()


def test_broker_rejects_credential_change_after_owner_approval(tmp_path: Path) -> None:
    with _running_broker(tmp_path) as (client, server):
        approved = client.put(BOT_A, "github", GITHUB_FIXTURE)
        snapshot = [
            {
                "provider": approved.provider,
                "last_four": approved.last_four,
                "updated_at": approved.updated_at,
                "env_name": approved.env_name or "",
            }
        ]
        client.put(BOT_A, "github", GITHUB_REPLACEMENT)
        with pytest.raises(ValueError, match="fresh approval"):
            client.execute(
                BOT_A,
                HOME_A,
                "gh auth status",
                credential_snapshot=snapshot,
            )
        assert server.executor.calls == []


def test_execution_bounds_cwd_timeout_and_output(tmp_path: Path) -> None:
    with _running_broker(tmp_path) as (client, _server):
        project = tmp_path / "homes" / HOME_A / "project"
        project.mkdir()
        cwd = client.execute(
            BOT_A,
            HOME_A,
            'python -c "from pathlib import Path; print(Path.cwd().name)"',
            cwd="project",
        )
        assert cwd.stdout.strip() == "project"
        with pytest.raises(ValueError, match="cwd"):
            client.execute(BOT_A, HOME_A, "pwd", cwd="../outside")
        timed = client.execute(
            BOT_A,
            HOME_A,
            'python -c "import time; time.sleep(2)"',
            timeout_seconds=0.1,
        )
        assert timed.ok is False
        assert timed.timed_out is True
        noisy = client.execute(
            BOT_A,
            HOME_A,
            "python -c \"print('x' * 100000)\"",
        )
        assert noisy.truncated is True
        assert len(noisy.stdout.encode()) <= 65_600


def test_private_store_mode_and_idempotent_legacy_migration(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    source = legacy / BOT_A
    source.mkdir(parents=True)
    old_secret = source / "registry-token"
    old_secret.write_text("reg_" + ("M" * 24), encoding="utf-8")
    old_secret.with_suffix(".meta").write_text(
        "MMMM\n2026-09-04T06:00:00Z\nREGISTRY_TOKEN\n",
        encoding="utf-8",
    )
    storage = PrivateCredentialStorage(tmp_path / "broker")
    try:
        first = migrate_legacy_credentials(legacy, storage)
        second = migrate_legacy_credentials(legacy, storage)
        assert first.migrated == 1
        assert first.failed == 0
        assert second.migrated == 0
        assert second.failed == 0
        assert not old_secret.exists()
        assert not old_secret.with_suffix(".meta").exists()
        assert storage.list_for_bot(BOT_A)[0].env_name == "REGISTRY_TOKEN"
        root_mode = stat.S_IMODE((tmp_path / "broker").stat().st_mode)
        db_mode = stat.S_IMODE(storage.path.stat().st_mode)
        assert root_mode == 0o700
        assert db_mode == 0o600
    finally:
        storage.close()


def test_migration_never_overwrites_newer_broker_value(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    source = legacy / BOT_A
    source.mkdir(parents=True)
    stale = "reg_" + ("S" * 24)
    current = "reg_" + ("N" * 24)
    old_secret = source / "registry-token"
    old_secret.write_text(stale, encoding="utf-8")
    storage = PrivateCredentialStorage(tmp_path / "broker")
    try:
        storage.put(BOT_A, "registry-token", current, env_name="REGISTRY_TOKEN")
        report = migrate_legacy_credentials(legacy, storage)
        assert report.migrated == 0
        assert report.stale_removed == 1
        assert report.failed == 0
        assert storage.confirm_secret(BOT_A, "registry-token", current)
        assert not storage.confirm_secret(BOT_A, "registry-token", stale)
        assert not old_secret.exists()
    finally:
        storage.close()


def test_migration_retries_confirm_and_unlink_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    legacy = tmp_path / "legacy"
    source = legacy / BOT_A
    source.mkdir(parents=True)
    old_secret = source / "registry-token"
    old_secret.write_text("reg_" + ("R" * 24), encoding="utf-8")
    storage = PrivateCredentialStorage(tmp_path / "broker")
    try:
        real_confirm = storage.confirm_secret
        monkeypatch.setattr(storage, "confirm_secret", lambda *_args: False)
        failed_confirm = migrate_legacy_credentials(legacy, storage)
        assert failed_confirm.failed == 1
        assert old_secret.exists()
        monkeypatch.setattr(storage, "confirm_secret", real_confirm)

        real_unlink = Path.unlink

        def fail_source_unlink(path: Path, *args, **kwargs):
            if path == old_secret:
                raise PermissionError("fixture unlink denied")
            return real_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_source_unlink)
        failed_unlink = migrate_legacy_credentials(legacy, storage)
        assert failed_unlink.failed == 1
        assert old_secret.exists()
        monkeypatch.setattr(Path, "unlink", real_unlink)
        recovered = migrate_legacy_credentials(legacy, storage)
        assert recovered.cleaned_existing == 1
        assert recovered.failed == 0
        assert not old_secret.exists()
    finally:
        storage.close()


def test_migration_skips_symlink_bot_directory(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    outside = tmp_path / "outside" / BOT_A
    outside.mkdir(parents=True)
    secret = outside / "github"
    secret.write_text(GITHUB_FIXTURE, encoding="utf-8")
    legacy.mkdir()
    (legacy / BOT_A).symlink_to(outside, target_is_directory=True)
    storage = PrivateCredentialStorage(tmp_path / "broker")
    try:
        report = migrate_legacy_credentials(legacy, storage)
        assert report == type(report)()
        assert secret.exists()
        assert storage.list_for_bot(BOT_A) == []
    finally:
        storage.close()


def test_broker_rejects_environment_control_names(tmp_path: Path) -> None:
    storage = PrivateCredentialStorage(tmp_path / "broker")
    try:
        for name in (
            "PATH",
            "HOME",
            "LANG",
            "LC_ALL",
            "GIT_TERMINAL_PROMPT",
            "BASH_ENV",
            "LD_PRELOAD",
            "PYTHONPATH",
        ):
            with pytest.raises(ValueError, match="reserved"):
                storage.put(BOT_A, "registry-token", "reg_" + ("Q" * 24), env_name=name)
    finally:
        storage.close()


def test_product_defaults_to_http_and_memory_broker_is_scripted_only(tmp_path: Path) -> None:
    base = {
        "agent_http_token": HOST_TOKEN,
        "credential_broker_token": "",
        "agent_data_dir": str(tmp_path),
    }
    live = credential_store_for_settings(
        SimpleNamespace(
            **base,
            agent_runtime="cursor",
            credential_broker_url="http://127.0.0.1:8431",
        )
    )
    assert isinstance(live, CredentialBrokerClient)
    scripted = credential_store_for_settings(
        SimpleNamespace(
            **base,
            agent_runtime="scripted",
            credential_broker_url="memory://tests",
        )
    )
    assert isinstance(scripted, InMemoryCredentialStore)
    with pytest.raises(ValueError, match="scripted"):
        credential_store_for_settings(
            SimpleNamespace(
                **base,
                agent_runtime="cursor",
                credential_broker_url="memory://not-production",
            )
        )


def test_broker_client_refuses_non_loopback_url() -> None:
    for url in ("https://example.com", "http://192.0.2.1:8431", "file:///tmp/broker"):
        with pytest.raises(ValueError, match="loopback"):
            CredentialBrokerClient(url, BROKER_TOKEN)
    for url in ("https://example.com", "http://192.0.2.1:8432", "file:///tmp/executor"):
        with pytest.raises(ValueError, match="loopback"):
            CredentialExecutorClient(url, EXECUTOR_TOKEN)
