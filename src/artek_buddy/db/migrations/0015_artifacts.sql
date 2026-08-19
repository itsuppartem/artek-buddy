CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL REFERENCES bots (id) ON DELETE CASCADE,
    run_id TEXT,
    name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size INT NOT NULL,
    storage_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS artifacts_bot_idx ON artifacts (bot_id, created_at DESC);
