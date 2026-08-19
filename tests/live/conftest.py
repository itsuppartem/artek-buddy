from __future__ import annotations

import os
import subprocess

import pytest

from tests.support import mask_secret


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("ARTEK_LIVE") != "1":
        skip = pytest.mark.skip(reason="live suite runs only on GitHub Actions with ARTEK_LIVE=1")
        for item in items:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def client_url() -> str:
    url = (os.environ.get("ARTEK_CLIENT_URL") or "").rstrip("/") + "/"
    if not url.startswith("http://127.0.0.1"):
        pytest.skip("ARTEK_CLIENT_URL must be loopback")
    return url


@pytest.fixture(scope="session")
def host_url() -> str:
    return (os.environ.get("ARTEK_HOST_URL") or "http://127.0.0.1:8080").rstrip("/")


def mint_pairing_code() -> str:
    raw = subprocess.check_output(
        ["docker", "exec", "artek-buddy", "python", "-m", "artek_buddy", "pair"],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    code = raw.strip().splitlines()[0].strip()
    mask_secret(code)
    return code
