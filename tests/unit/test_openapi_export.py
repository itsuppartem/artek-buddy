from __future__ import annotations

import json

from artek_buddy.main import app
from artek_buddy.openapi_export import SCHEMA_PATH, dump_openapi


def test_runtime_openapi_urls_are_disabled() -> None:
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_committed_openapi_matches_app_schema() -> None:
    assert SCHEMA_PATH.is_file()
    assert SCHEMA_PATH.read_text(encoding="utf-8") == dump_openapi()


def test_dumped_schema_includes_health_and_bots() -> None:
    document = json.loads(dump_openapi())
    assert "/health" in document["paths"]
    assert "/v1/bots" in document["paths"]
    assert "HealthResponse" in document["components"]["schemas"]
    assert all(not path.startswith("/novnc") for path in document["paths"])
