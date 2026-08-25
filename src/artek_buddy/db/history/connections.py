from __future__ import annotations

from artek_buddy.connections.broker import reset_fake_broker
from artek_buddy.contracts.domain import Connection, ConnectionKeyStatus, ConnectionList
from artek_buddy.db.shaping import isoformat_utc, new_id, parse_iso
from artek_buddy.model_catalog import last_four


class ConnectionsMixin:
    def clear_connections(self) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM connections")
            conn.execute("DELETE FROM connection_key")
            conn.commit()
        reset_fake_broker()

    def connection_key_status(self) -> ConnectionKeyStatus:
        row = self._key_row()
        has_key = bool(row and row.get("api_key"))
        return ConnectionKeyStatus(
            configured=has_key,
            last_four=str(row["last_four"]) if row and row.get("last_four") else None,
        )

    def raw_connection_key(self) -> str | None:
        row = self._key_row()
        key = (row or {}).get("api_key") if row else None
        return str(key).strip() if key else None

    def seed_env_connection_key(self, key: str) -> None:
        incoming = (key or "").strip()
        if not incoming or self.raw_connection_key():
            return
        self.save_connection_key(incoming)

    def save_connection_key(self, key: str) -> ConnectionKeyStatus:
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO connection_key (id, api_key, last_four, updated_at)
                VALUES (1, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    api_key = EXCLUDED.api_key,
                    last_four = EXCLUDED.last_four,
                    updated_at = EXCLUDED.updated_at
                """,
                (key.strip(), last_four(key), now),
            )
            conn.commit()
        return self.connection_key_status()

    def clear_connection_key(self) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM connections")
            conn.execute("DELETE FROM connection_key")
            conn.commit()
        reset_fake_broker()

    def list_connections(self) -> ConnectionList:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM connections
                ORDER BY created_at ASC
                """
            ).fetchall()
            conn.commit()
        return ConnectionList(connections=[self._connection_view(row) for row in rows])

    def connected_slugs(self) -> set[str]:
        return {
            row.provider for row in self.list_connections().connections if row.status == "connected"
        }

    def connection_remote_id(self, connection_id: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT remote_id FROM connections WHERE id = %s",
                (connection_id,),
            ).fetchone()
            conn.commit()
        remote = (row or {}).get("remote_id") if row else None
        return str(remote) if remote else None

    def get_connection(self, connection_id: str) -> Connection | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM connections WHERE id = %s",
                (connection_id,),
            ).fetchone()
            conn.commit()
        return self._connection_view(row) if row else None

    def active_for_provider(self, provider: str) -> Connection | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM connections
                WHERE provider = %s AND status IN ('pending', 'connected')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (provider,),
            ).fetchone()
            conn.commit()
        return self._connection_view(row) if row else None

    def insert_connection(
        self,
        *,
        provider: str,
        display_name: str,
        status: str,
        capabilities: list[str],
        no_auth: bool,
        remote_id: str | None,
    ) -> Connection:
        now = isoformat_utc()
        connection_id = new_id("conn")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO connections (
                    id, provider, display_name, status, capabilities,
                    no_auth, remote_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    connection_id,
                    provider,
                    display_name,
                    status,
                    capabilities,
                    no_auth,
                    remote_id,
                    now,
                    now,
                ),
            )
            conn.commit()
        found = self.get_connection(connection_id)
        assert found is not None
        return found

    def update_connection(
        self,
        connection_id: str,
        *,
        status: str | None = None,
        capabilities: list[str] | None = None,
    ) -> Connection | None:
        current = self.get_connection(connection_id)
        if current is None:
            return None
        now = isoformat_utc()
        next_status = status or current.status
        next_caps = capabilities if capabilities is not None else current.capabilities
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE connections
                SET status = %s, capabilities = %s, updated_at = %s
                WHERE id = %s
                """,
                (next_status, next_caps, now, connection_id),
            )
            conn.commit()
        return self.get_connection(connection_id)

    def connection_for_tool(self, name: str) -> Connection | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM connections
                WHERE status = 'connected' AND %s = ANY (capabilities)
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (name,),
            ).fetchone()
            conn.commit()
        return self._connection_view(row) if row else None

    def _key_row(self):
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM connection_key WHERE id = 1").fetchone()
            conn.commit()
        return row

    def _connection_view(self, row) -> Connection:
        caps = row.get("capabilities") or []
        return Connection(
            id=str(row["id"]),
            provider=str(row["provider"]),
            display_name=str(row["display_name"]),
            status=str(row["status"]),
            capabilities=[str(item) for item in caps],
            created_at=parse_iso(row["created_at"]),
        )
