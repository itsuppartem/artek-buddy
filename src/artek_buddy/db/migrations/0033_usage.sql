CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    bot_id TEXT REFERENCES bots (id) ON DELETE CASCADE,
    run_id TEXT UNIQUE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    cache_read_tokens INT NOT NULL DEFAULT 0,
    cache_write_tokens INT NOT NULL DEFAULT 0,
    reasoning_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS usage_records_bot_idx
    ON usage_records (bot_id, created_at DESC);
