from __future__ import annotations

import importlib.util
from pathlib import Path

WEB_PATHS = Path(__file__).resolve().parents[2] / "client" / "web_paths.py"


def _mod():
    spec = importlib.util.spec_from_file_location("artek_web_paths", WEB_PATHS)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_web_file_stays_inside_root(tmp_path: Path) -> None:
    web = _mod()
    root = tmp_path / "web"
    root.mkdir()
    (root / "index.html").write_text("ok")
    nested = root / "assets"
    nested.mkdir()
    (nested / "app.js").write_text("js")
    assert web.web_file_for_request(root, "/assets/app.js") == (nested / "app.js").resolve()
    assert web.web_file_for_request(root, "/../etc/passwd") is None
    assert web.web_file_for_request(root, "/x\r\nSet-Cookie:x") is None
    ctype = web.safe_content_type(nested / "app.js")
    assert "\r" not in ctype and "\n" not in ctype
