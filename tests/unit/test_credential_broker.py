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
from artek_buddy.bot_credentials import InMemoryCredentialStore
from artek_buddy.credential_broker import (
    CredentialBrokerClient,
    PrivateCredentialStorage,
    credential_store_for_settings,
    make_credential_broker_server,
    migrate_legacy_credentials,
)
from artek_buddy.credential_executor import (
    CredentialExecutorClient,
    credential_executor_authorized,
    make_credential_executor_server,
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
    executor_server = make_credential_executor_server(
        token=EXECUTOR_TOKEN,
        homes_root=homes,
        port=0,
        forking=False,
    )
    executor_thread = threading.Thread(target=executor_server.serve_forever, daemon=True)
    executor_thread.start()
    executor = CredentialExecutorClient(
        f"http://127.0.0.1:{executor_server.server_port}",
        EXECUTOR_TOKEN,
    )
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
        executor_server.shutdown()
        executor_server.server_close()
        executor_thread.join(timeout=2)
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
    with _running_broker(tmp_path) as (client, _server):
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


def test_replace_forget_named_env_and_no_process_environment_mutation(tmp_path: Path) -> None:
    original_environment = dict(os.environ)
    replacement_hash = hashlib.sha256(GITHUB_REPLACEMENT.encode()).hexdigest()
    named = "reg_" + ("Z" * 24)
    with _running_broker(tmp_path) as (client, _server):
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
    assert dict(os.environ) == original_environment
    assert GITHUB_FIXTURE not in os.environ.values()
    assert GITHUB_REPLACEMENT not in os.environ.values()


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


def test_executor_uses_distinct_derived_bearer() -> None:
    assert credential_executor_authorized(f"Bearer {EXECUTOR_TOKEN}", EXECUTOR_TOKEN)
    assert not credential_executor_authorized(f"Bearer {HOST_TOKEN}", EXECUTOR_TOKEN)
    assert not credential_executor_authorized(f"Bearer {BROKER_TOKEN}", EXECUTOR_TOKEN)


def test_broker_client_refuses_non_loopback_url() -> None:
    for url in ("https://example.com", "http://192.0.2.1:8431", "file:///tmp/broker"):
        with pytest.raises(ValueError, match="loopback"):
            CredentialBrokerClient(url, BROKER_TOKEN)
    for url in ("https://example.com", "http://192.0.2.1:8432", "file:///tmp/executor"):
        with pytest.raises(ValueError, match="loopback"):
            CredentialExecutorClient(url, EXECUTOR_TOKEN)
