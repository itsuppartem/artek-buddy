from __future__ import annotations

import json
import logging
from io import StringIO
from pathlib import Path

from artek_buddy.observe import JsonFormatter, configure_logging

ROOT = Path(__file__).resolve().parents[2]


def test_basicconfig_lives_only_in_observe() -> None:
    hits = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src" / "artek_buddy").rglob("*.py")
        if "logging.basicConfig" in path.read_text(encoding="utf-8")
    ]
    assert hits == ["src/artek_buddy/observe.py"]


def test_json_logging_survives_http_router_import() -> None:
    import artek_buddy.http.bots  # noqa: F401
    import artek_buddy.http.turns  # noqa: F401

    configure_logging(log_format="json", force=True)
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("artek_buddy.logging_entry_probe")
    log.handlers = [handler]
    log.propagate = False
    log.setLevel(logging.INFO)
    log.info("json-probe-after-router")
    payload = json.loads(stream.getvalue())
    assert payload["msg"] == "json-probe-after-router"
