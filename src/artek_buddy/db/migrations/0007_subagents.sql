CREATE TABLE IF NOT EXISTS subagents (
    id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL REFERENCES bots(id),
    thread_id TEXT NOT NULL,
    parent_run_id TEXT,
    cursor_agent_id TEXT,
    seq INT NOT NULL,
    name TEXT NOT NULL,
    task TEXT NOT NULL,
    status TEXT NOT NULL,
    progress TEXT,
    thinking TEXT,
    result TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS subagents_bot_seq_idx ON subagents (bot_id, seq DESC);
CREATE INDEX IF NOT EXISTS subagents_bot_status_idx ON subagents (bot_id, status);

CREATE TABLE IF NOT EXISTS turn_inbox (
    id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL REFERENCES bots(id),
    message_id TEXT NOT NULL REFERENCES messages(id),
    text TEXT NOT NULL,
    reply_to_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS turn_inbox_bot_idx ON turn_inbox (bot_id, created_at);
