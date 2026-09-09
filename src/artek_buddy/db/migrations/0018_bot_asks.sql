CREATE TABLE IF NOT EXISTS bot_asks (
    id TEXT PRIMARY KEY,
    from_bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    to_bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    from_run_id TEXT,
    to_run_id TEXT,
    question TEXT NOT NULL,
    reply_text TEXT,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS bot_asks_to_run_idx ON bot_asks (to_run_id);
CREATE INDEX IF NOT EXISTS bot_asks_to_pending_idx ON bot_asks (to_bot_id, created_at)
    WHERE delivered_at IS NULL AND to_run_id IS NULL;
