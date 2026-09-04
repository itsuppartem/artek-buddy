from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.api.postgres_setup import report_postgres_setup_error

from artek_buddy.db.history import HistoryStore


@pytest.fixture(scope="session")
def postgres_ok() -> None:
    store = HistoryStore(os.environ["DATABASE_URL"])
    try:
        store.open()
        store.apply_migrations()
        store.ensure_workspace()
    except Exception as err:
        report_postgres_setup_error(err)
    finally:
        store.close()


@pytest.fixture
def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, postgres_ok: None, host_token: str
) -> Iterator[TestClient]:
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("AGENT_DATA_DIR", str(data))
    monkeypatch.setenv("AGENT_CWD", str(tmp_path / "workspace"))
    monkeypatch.setenv("AGENT_RUNTIME", "scripted")
    monkeypatch.setenv("SANDBOX_PROVIDER", "fake")
    monkeypatch.setenv("CURSOR_API_KEY", "")
    monkeypatch.setenv("COMPOSIO_API_KEY", "")
    monkeypatch.setenv("AGENT_HTTP_TOKEN", host_token)
    monkeypatch.setenv("CREDENTIAL_BROKER_URL", "memory://api-tests")
    monkeypatch.chdir(tmp_path)

    from artek_buddy.main import app

    with TestClient(app) as session:
        yield session


@pytest.fixture(autouse=True)
def seed_default_model(client: TestClient, request: pytest.FixtureRequest) -> None:
    store = client.app.state.store
    store.clear_model_state()
    store.clear_connections()
    if "no_model_seed" not in request.keywords:
        store.seed_scripted_default()


@pytest.fixture(autouse=True)
def reset_pairing_limiter() -> Iterator[None]:
    from artek_buddy.auth import pairing_attempts

    pairing_attempts._hits.clear()
    yield
    pairing_attempts._hits.clear()
