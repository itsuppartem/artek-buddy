from __future__ import annotations

import sys
from pathlib import Path

import pytest


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
        ("http://127.0.0.1:8080http://127.0.0.1:8080", False),
        ("http://127.0.0.1:8080http:", False),
    ],
)
def test_pairing_url_allowed(client_mod, url: str, ok: bool) -> None:
    assert client_mod.pairing_url_allowed(url) is ok


def test_proxy_origin_must_be_loopback_same_port(client_mod) -> None:
    assert client_mod.proxy_origin_allowed("http://127.0.0.1:7777", "same-origin", 7777) is True
    assert client_mod.proxy_origin_allowed("http://127.0.0.1:80", "same-origin", 7777) is False
    assert client_mod.proxy_origin_allowed("http://evil.example", "same-origin", 7777) is False
    assert client_mod.proxy_origin_allowed("http://127.0.0.1:7777", "cross-site", 7777) is False


def test_write_text_sets_mode(client_mod, tmp_path: Path) -> None:
    pairing = sys.modules["pairing"]
    path = tmp_path / "token"
    pairing._write_text(path, "dev_example", 0o600)
    assert path.read_text(encoding="utf-8") == "dev_example\n"
    assert path.stat().st_mode & 0o777 == 0o600
