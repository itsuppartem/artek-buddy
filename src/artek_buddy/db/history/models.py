from __future__ import annotations

from typing import Any

from artek_buddy.contracts.domain import ModelCredential, ModelCredentialList
from artek_buddy.db.shaping import isoformat_utc
from artek_buddy.model_catalog import (
    PROVIDERS,
    is_placeholder_key,
    last_four,
    provider_label,
)


class ModelsMixin:
    def clear_model_state(self) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM model_catalog")
            conn.execute("DELETE FROM model_defaults")
            conn.execute("DELETE FROM model_credentials")
            conn.commit()

    def seed_env_cursor(self, key: str) -> None:
        if is_placeholder_key(key):
            return
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO model_credentials (provider, api_key, last_four, last_error, updated_at)
                SELECT 'cursor', %s, %s, NULL, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM model_credentials WHERE provider = 'cursor'
                )
                """,
                (key.strip(), last_four(key), now),
            )
            conn.commit()

    def list_credentials(self) -> ModelCredentialList:
        default = self.get_default_model()
        stored = {row["provider"]: row for row in self._credential_rows()}
        rows = [self._credential_view(spec.id, stored.get(spec.id), default) for spec in PROVIDERS]
        return ModelCredentialList(
            credentials=rows,
            default_provider=default[0] if default else None,
            default_model=default[1] if default else None,
        )

    def raw_key(self, provider: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT api_key FROM model_credentials WHERE provider = %s",
                (provider,),
            ).fetchone()
            conn.commit()
        key = (row or {}).get("api_key") if row else None
        return str(key).strip() if key else None

    def save_key(self, provider: str, key: str) -> ModelCredential:
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO model_credentials (provider, api_key, last_four, last_error, updated_at)
                VALUES (%s, %s, %s, NULL, %s)
                ON CONFLICT (provider) DO UPDATE SET
                    api_key = EXCLUDED.api_key,
                    last_four = EXCLUDED.last_four,
                    last_error = NULL,
                    updated_at = EXCLUDED.updated_at
                """,
                (provider, key.strip(), last_four(key), now),
            )
            conn.commit()
        return self.list_credentials_row(provider)

    def set_credential_error(self, provider: str, message: str | None) -> ModelCredential:
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE model_credentials
                SET last_error = %s, updated_at = %s
                WHERE provider = %s
                """,
                (message, now, provider),
            )
            conn.commit()
        return self.list_credentials_row(provider)

    def forget_key(self, provider: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE model_credentials
                SET api_key = NULL, last_four = NULL, last_error = NULL, updated_at = %s
                WHERE provider = %s
                """,
                (isoformat_utc(), provider),
            )
            conn.execute("DELETE FROM model_catalog WHERE provider = %s", (provider,))
            conn.execute(
                "DELETE FROM model_defaults WHERE provider = %s",
                (provider,),
            )
            conn.commit()

    def replace_catalog(self, provider: str, model_ids: list[str]) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM model_catalog WHERE provider = %s", (provider,))
            for model_id in model_ids:
                conn.execute(
                    """
                    INSERT INTO model_catalog (provider, model_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (provider, model_id),
                )
            conn.commit()

    def list_catalog(self) -> list[dict[str, str]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT c.provider, c.model_id
                FROM model_catalog c
                JOIN model_credentials k ON k.provider = c.provider
                WHERE k.api_key IS NOT NULL AND k.api_key <> ''
                ORDER BY c.provider, c.model_id
                """
            ).fetchall()
            conn.commit()
        return [{"id": str(row["model_id"]), "provider": str(row["provider"])} for row in rows]

    def catalog_ids(self, provider: str) -> set[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT model_id FROM model_catalog WHERE provider = %s",
                (provider,),
            ).fetchall()
            conn.commit()
        return {str(row["model_id"]) for row in rows}

    def get_default_model(self) -> tuple[str, str] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT provider, model_id FROM model_defaults WHERE id = 1"
            ).fetchone()
            conn.commit()
        if row is None or not row.get("provider") or not row.get("model_id"):
            return None
        return str(row["provider"]), str(row["model_id"])

    def set_default_model(self, provider: str, model_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO model_defaults (id, provider, model_id)
                VALUES (1, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    provider = EXCLUDED.provider,
                    model_id = EXCLUDED.model_id
                """,
                (provider, model_id),
            )
            conn.commit()

    def seed_scripted_default(self) -> None:
        self.save_key("openrouter", "test-secret-seed")
        self.replace_catalog("openrouter", ["scripted"])
        self.set_default_model("openrouter", "scripted")

    def list_credentials_row(self, provider: str) -> ModelCredential:
        default = self.get_default_model()
        stored = {row["provider"]: row for row in self._credential_rows()}
        return self._credential_view(provider, stored.get(provider), default)

    def _credential_rows(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM model_credentials").fetchall()
            conn.commit()
        return list(rows)

    def _credential_view(
        self,
        provider: str,
        row: dict[str, Any] | None,
        default: tuple[str, str] | None,
    ) -> ModelCredential:
        has_key = bool(row and row.get("api_key"))
        return ModelCredential(
            id=f"cred_{provider}",
            provider=provider,
            label=provider_label(provider),
            has_key=has_key,
            last_four=str(row["last_four"]) if row and row.get("last_four") else None,
            is_default=bool(default and default[0] == provider),
            error=str(row["last_error"]) if row and row.get("last_error") else None,
        )
