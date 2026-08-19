from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parents[2] / "client" / "artek_buddy.py"


@pytest.fixture(scope="module")
def client_mod():
    spec = importlib.util.spec_from_file_location("artek_buddy_client", CLIENT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("http://127.0.0.1:8080", True),
        ("http://localhost:8080", True),
        ("https://machine.ts.net", True),
        ("http://100.64.1.2:8080", True),
        ("http://192.168.1.10:8080", True),
        ("https://evil.example", False),
        ("ftp://127.0.0.1", False),
        ("", False),
    ],
)
def test_pairing_url_allowed(client_mod, url: str, ok: bool) -> None:
    assert client_mod.pairing_url_allowed(url) is ok


def test_proxy_origin_must_be_loopback_same_port(client_mod) -> None:
    assert client_mod.proxy_origin_allowed("http://127.0.0.1:7777", "same-origin", 7777) is True
    assert client_mod.proxy_origin_allowed("http://127.0.0.1:80", "same-origin", 7777) is False
    assert client_mod.proxy_origin_allowed("http://evil.example", "same-origin", 7777) is False
    assert client_mod.proxy_origin_allowed("http://127.0.0.1:7777", "cross-site", 7777) is False
