from __future__ import annotations

from typing import Any

from artek_buddy.contracts.domain import UsageRecord, UsageRecordList, UsageSummary
from artek_buddy.db.shaping import isoformat_utc, new_id, parse_iso
from artek_buddy.usage_cost import estimate_cost_usd_micros, micros_to_usd

_LIST_TAIL = " ORDER BY created_at DESC LIMIT %s"


def _usd_from_row(row: dict[str, Any]) -> float | None:
    raw = row.get("cost_usd_micros")
    if raw is None:
        return None
    return micros_to_usd(int(raw))


def _usage_filter_sql(
    select: str,
    *,
    bot_id: str | None,
    run_id: str | None,
    order_limit: bool,
) -> tuple[str, list[Any]]:
    params: list[Any] = []
    if bot_id and run_id:
        sql = select + " WHERE bot_id = %s AND run_id = %s"
        params.extend([bot_id, run_id])
    elif bot_id:
        sql = select + " WHERE bot_id = %s"
        params.append(bot_id)
    elif run_id:
        sql = select + " WHERE run_id = %s"
        params.append(run_id)
    else:
        sql = select
    if order_limit:
        sql += _LIST_TAIL
    return sql, params


class UsageMixin:
    def get_run_fast(self, run_id: str) -> bool | None:
        if not run_id:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT fast FROM run_usage_fast WHERE run_id = %s",
                (run_id,),
            ).fetchone()
            conn.commit()
        if row is None:
            return None
        return bool(row["fast"])

    def bind_run_fast(self, run_id: str, fast: bool | None = None) -> bool:
        """Snapshot Fast for this run. The first write wins; later Models defaults do not."""
        if not run_id:
            return True if fast is None else bool(fast)
        existing = self.get_run_fast(run_id)
        if existing is not None:
            return existing
        if fast is None:
            _, stored = self.get_model_params()
            use_fast = True if stored is None else bool(stored)
        else:
            use_fast = bool(fast)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO run_usage_fast (run_id, fast)
                VALUES (%s, %s)
                ON CONFLICT (run_id) DO NOTHING
                """,
                (run_id, use_fast),
            )
            conn.commit()
        bound = self.get_run_fast(run_id)
        return True if bound is None else bool(bound)

    def record_usage(
        self,
        *,
        bot_id: str | None,
        run_id: str | None,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        reasoning_tokens: int = 0,
        total_tokens: int = 0,
        fast: bool | None = None,
    ) -> UsageRecord | None:
        now = isoformat_utc()
        record_id = new_id("usage")
        use_fast = True if fast is None else bool(fast)
        cost_usd_micros = estimate_cost_usd_micros(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            fast=use_fast,
        )
        with self._conn() as conn:
            row = conn.execute(
                """
                INSERT INTO usage_records (
                    id, bot_id, run_id, provider, model,
                    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                    reasoning_tokens, total_tokens, cost_usd_micros, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id)
                DO UPDATE SET
                    provider = EXCLUDED.provider,
                    model = EXCLUDED.model,
                    input_tokens = EXCLUDED.input_tokens,
                    output_tokens = EXCLUDED.output_tokens,
                    cache_read_tokens = EXCLUDED.cache_read_tokens,
                    cache_write_tokens = EXCLUDED.cache_write_tokens,
                    reasoning_tokens = EXCLUDED.reasoning_tokens,
                    total_tokens = EXCLUDED.total_tokens,
                    cost_usd_micros = EXCLUDED.cost_usd_micros
                RETURNING *
                """,
                (
                    record_id,
                    bot_id,
                    run_id,
                    provider or "unknown",
                    model or "unknown",
                    input_tokens,
                    output_tokens,
                    cache_read_tokens,
                    cache_write_tokens,
                    reasoning_tokens,
                    total_tokens,
                    cost_usd_micros,
                    now,
                ),
            ).fetchone()
            conn.commit()
        if row is None:
            return None
        return self._usage_from_row(row)

    def list_usage(
        self,
        *,
        bot_id: str | None = None,
        run_id: str | None = None,
        limit: int = 100,
    ) -> UsageRecordList:
        capped = max(1, min(limit, 200))
        sql, params = _usage_filter_sql(
            "SELECT * FROM usage_records",
            bot_id=bot_id,
            run_id=run_id,
            order_limit=True,
        )
        params.append(capped)
        with self._conn() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            conn.commit()
        return UsageRecordList(records=[self._usage_from_row(row) for row in rows])

    def usage_summary(
        self,
        *,
        bot_id: str | None = None,
        run_id: str | None = None,
    ) -> UsageSummary:
        sql, params = _usage_filter_sql(
            """
            SELECT
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(cache_read_tokens), 0) AS cache_read_tokens,
                COALESCE(SUM(cache_write_tokens), 0) AS cache_write_tokens,
                COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                SUM(cost_usd_micros) AS cost_usd_micros,
                COUNT(*)::int AS runs
            FROM usage_records
            """,
            bot_id=bot_id,
            run_id=run_id,
            order_limit=False,
        )
        with self._conn() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
            conn.commit()
        row = row or {}
        return UsageSummary(
            input_tokens=int(row.get("input_tokens") or 0),
            output_tokens=int(row.get("output_tokens") or 0),
            cache_read_tokens=int(row.get("cache_read_tokens") or 0),
            cache_write_tokens=int(row.get("cache_write_tokens") or 0),
            reasoning_tokens=int(row.get("reasoning_tokens") or 0),
            total_tokens=int(row.get("total_tokens") or 0),
            estimated_cost_usd=_usd_from_row(row),
            runs=int(row.get("runs") or 0),
        )

    def _usage_from_row(self, row: dict[str, Any]) -> UsageRecord:
        return UsageRecord(
            id=row["id"],
            bot_id=row.get("bot_id"),
            run_id=row.get("run_id"),
            provider=str(row.get("provider") or ""),
            model=str(row.get("model") or ""),
            input_tokens=int(row.get("input_tokens") or 0),
            output_tokens=int(row.get("output_tokens") or 0),
            cache_read_tokens=int(row.get("cache_read_tokens") or 0),
            cache_write_tokens=int(row.get("cache_write_tokens") or 0),
            reasoning_tokens=int(row.get("reasoning_tokens") or 0),
            total_tokens=int(row.get("total_tokens") or 0),
            estimated_cost_usd=_usd_from_row(row),
            created_at=parse_iso(row["created_at"]),
        )
