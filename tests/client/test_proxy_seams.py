from __future__ import annotations

from pathlib import Path

CLIENT = Path(__file__).resolve().parents[2] / "client"


def test_static_bytes_and_owner_exec_live_in_different_modules() -> None:
    proxy = (CLIENT / "proxy.py").read_text(encoding="utf-8")
    rpc = (CLIENT / "proxy_rpc.py").read_text(encoding="utf-8")
    static = (CLIENT / "proxy_static.py").read_text(encoding="utf-8")
    upstream = (CLIENT / "proxy_upstream.py").read_text(encoding="utf-8")
    assert "subprocess.run" not in proxy
    assert "shell=True" not in proxy
    assert "web_file_for_request" not in proxy
    assert "shell=True" in rpc
    assert "lgtm[py/command-line-injection]" in rpc
    assert "web_file_for_request" in static
    assert "novnc" in proxy.lower() or "websocket" in upstream.lower()
