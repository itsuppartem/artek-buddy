"""Dump the FastAPI schema for the window TypeScript generator.

Runtime /docs, /redoc, and /openapi.json stay off. This module is a build/CI
tool, not an HTTP route.
"""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "client" / "web" / "openapi.json"


def openapi_document() -> dict:
    from artek_buddy.main import app

    return app.openapi()


def dump_openapi() -> str:
    return json.dumps(openapi_document(), indent=2, sort_keys=True) + "\n"


def write_openapi(path: Path | None = None) -> Path:
    dest = path or SCHEMA_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(dump_openapi(), encoding="utf-8")
    return dest


def main() -> None:
    print(write_openapi())


if __name__ == "__main__":
    main()
