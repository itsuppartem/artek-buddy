CREATE TABLE IF NOT EXISTS routines (
    id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL REFERENCES bots(id),
    name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    cron TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    active BOOLEAN NOT NULL DEFAULT FALSE,
    notify BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS routines_bot_idx ON routines (bot_id);
CREATE INDEX IF NOT EXISTS routines_due_idx ON routines (active, next_run_at);
