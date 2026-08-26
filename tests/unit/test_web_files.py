from __future__ import annotations

from pathlib import Path

from artek_buddy.web_files import safe_content_type, web_file_for_request


def test_web_file_stays_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "web"
    root.mkdir()
    (root / "index.html").write_text("ok", encoding="utf-8")
    nested = root / "assets"
    nested.mkdir()
    (nested / "app.js").write_text("js", encoding="utf-8")
    (root / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    assert web_file_for_request(root, "/assets/app.js") == (nested / "app.js").resolve()
    assert web_file_for_request(root, "/app") == (root / "index.html").resolve()
    assert web_file_for_request(root, "/../etc/passwd") is None
    assert web_file_for_request(root, "/x\r\nSet-Cookie:x") is None
    assert safe_content_type(root / "manifest.webmanifest") == "application/manifest+json"
    ctype = safe_content_type(nested / "app.js")
    assert "\r" not in ctype and "\n" not in ctype
