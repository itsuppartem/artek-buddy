"""Loopback memory index. Same capture/recall verbs as TencentDB Agent Memory.

The official Node gateway can replace this process later. We do not call
Tencent Cloud or a second model. Cursor writes; this process only stores
and searches on 127.0.0.1.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from artek_buddy.memory_hub import MemoryEntry, is_expired

log = logging.getLogger("artek_buddy")


class GatewayClient:
    def __init__(self, base_url: str, timeout: float = 1.0) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.base_url:
            return None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                raw = resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            log.warning("memory gateway unavailable: %s", err)
            return None
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def capture(self, entry: MemoryEntry, user_id: str, agent_id: str | None) -> None:
        self._post(
            "/capture",
            {
                "id": entry.id,
                "user_id": user_id,
                "agent_id": agent_id,
                "scope": entry.scope,
                "kind": entry.kind,
                "text": entry.text,
                "source": entry.source,
                "shelf": entry.shelf,
                "until": entry.until,
            },
        )

    def recall(self, user_id: str, query: str, agent_id: str | None, limit: int) -> list[MemoryEntry]:
        body = self._post(
            "/recall",
            {"user_id": user_id, "query": query, "agent_id": agent_id, "limit": limit},
        )
        rows = (body or {}).get("entries") or []
        entries: list[MemoryEntry] = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("id") or not row.get("text"):
                continue
            entries.append(
                MemoryEntry(
                    id=str(row["id"]),
                    scope=str(row.get("scope") or "user"),
                    kind=str(row.get("kind") or "preference"),
                    text=str(row["text"]),
                    source=str(row.get("source") or "gateway"),
                    bot_id=row.get("agent_id"),
                    shelf=str(row.get("shelf") or "owner"),
                    until=row.get("until"),
                )
            )
        return entries

    def delete(self, entry_id: str) -> None:
        self._post("/delete", {"id": entry_id})


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            agent_id TEXT,
            scope TEXT NOT NULL,
            kind TEXT NOT NULL,
            text TEXT NOT NULL,
            source TEXT NOT NULL,
            shelf TEXT NOT NULL DEFAULT 'owner',
            until TEXT
        )
        """
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(entries)").fetchall()}
    if "shelf" not in cols:
        conn.execute("ALTER TABLE entries ADD COLUMN shelf TEXT NOT NULL DEFAULT 'owner'")
    if "until" not in cols:
        conn.execute("ALTER TABLE entries ADD COLUMN until TEXT")
    conn.commit()
    return conn


class _Handler(BaseHTTPRequestHandler):
    server_version = "ArtekMemoryGateway/1"

    def log_message(self, *_args: object) -> None:
        return

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            value = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/health":
            self._json(200, {"ok": True})
            return
        self._json(404, {"ok": False})

    def do_POST(self) -> None:
        conn: sqlite3.Connection = self.server.conn  # type: ignore[attr-defined]
        path = urlparse(self.path).path
        body = self._body()
        if path == "/capture":
            conn.execute(
                """
                INSERT OR REPLACE INTO entries
                (id, user_id, agent_id, scope, kind, text, source, shelf, until)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(body.get("id") or ""),
                    str(body.get("user_id") or "owner"),
                    body.get("agent_id"),
                    str(body.get("scope") or "user"),
                    str(body.get("kind") or "preference"),
                    str(body.get("text") or ""),
                    str(body.get("source") or "remember"),
                    str(body.get("shelf") or "owner"),
                    body.get("until"),
                ),
            )
            conn.commit()
            self._json(200, {"ok": True})
            return
        if path == "/recall":
            query = str(body.get("query") or "").lower()
            agent_id = body.get("agent_id")
            limit = max(1, min(int(body.get("limit") or 8), 32))
            rows = conn.execute(
                "SELECT id, agent_id, scope, kind, text, source, shelf, until FROM entries WHERE user_id = ?",
                (str(body.get("user_id") or "owner"),),
            ).fetchall()
            parts = [part for part in query.split() if len(part) > 2]
            hits = []
            if query:
                for row in rows:
                    if row["scope"] == "bot" and row["agent_id"] not in {None, agent_id}:
                        continue
                    until = row["until"] if "until" in row.keys() else None
                    if until and is_expired(
                        MemoryEntry(
                            id=str(row["id"]),
                            scope=str(row["scope"] or "user"),
                            kind=str(row["kind"] or "preference"),
                            text=str(row["text"] or ""),
                            source=str(row["source"] or "gateway"),
                            until=str(until),
                        )
                    ):
                        continue
                    blob = f"{row['kind']} {row['text']}".lower()
                    if query not in blob and not any(part in blob for part in parts):
                        continue
                    hits.append(
                        {
                            "id": row["id"],
                            "agent_id": row["agent_id"],
                            "scope": row["scope"],
                            "kind": row["kind"],
                            "text": row["text"],
                            "source": row["source"],
                            "shelf": row["shelf"] if "shelf" in row.keys() else "owner",
                            "until": row["until"] if "until" in row.keys() else None,
                        }
                    )
                    if len(hits) >= limit:
                        break
            self._json(200, {"entries": hits})
            return
        if path == "/delete":
            conn.execute("DELETE FROM entries WHERE id = ?", (str(body.get("id") or ""),))
            conn.commit()
            self._json(200, {"ok": True})
            return
        self._json(404, {"ok": False})


def make_gateway_server(data_dir: str, host: str = "127.0.0.1", port: int = 8420) -> ThreadingHTTPServer:
    db = Path(data_dir) / "memory.sqlite"
    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.conn = _connect(db)  # type: ignore[attr-defined]
    return httpd


def serve_gateway(data_dir: str, host: str = "127.0.0.1", port: int = 8420) -> None:
    httpd = make_gateway_server(data_dir, host, port)
    log.info("memory gateway listening on %s:%s db=%s", host, port, Path(data_dir) / "memory.sqlite")
    try:
        httpd.serve_forever()
    finally:
        httpd.conn.close()  # type: ignore[attr-defined]


def main() -> int:
    host = os.environ.get("MEMORY_GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("MEMORY_GATEWAY_PORT", "8420"))
    data_dir = os.environ.get("MEMORY_GATEWAY_DIR", "/data/agent-memory")
    serve_gateway(data_dir, host, port)
    return 0
