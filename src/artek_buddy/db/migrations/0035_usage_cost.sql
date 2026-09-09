ALTER TABLE usage_records
    ADD COLUMN IF NOT EXISTS cost_usd_micros BIGINT;
