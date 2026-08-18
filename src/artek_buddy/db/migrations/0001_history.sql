CREATE TABLE IF NOT EXISTS schema_migrations (
    id TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bots (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    name TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '#3EC5A8',
    notify_on_finish BOOLEAN NOT NULL DEFAULT TRUE,
    pinned BOOLEAN NOT NULL DEFAULT FALSE,
    archived_at TIMESTAMPTZ,
    unread BOOLEAN NOT NULL DEFAULT FALSE,
    parent_bot_id TEXT,
    thread_id TEXT NOT NULL,
    preview TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'idle',
    computer_mode TEXT NOT NULL DEFAULT 'team',
    cursor_agent_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL UNIQUE REFERENCES bots(id),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id),
    seq INT NOT NULL,
    role TEXT NOT NULL,
    blocks JSONB NOT NULL,
    run_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (thread_id, seq)
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL REFERENCES bots(id),
    thread_id TEXT NOT NULL REFERENCES threads(id),
    task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    trigger TEXT NOT NULL,
    model_provider TEXT,
    model_id TEXT,
    error TEXT,
    result TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS bots_cursor_agent_id_idx ON bots (cursor_agent_id);
CREATE INDEX IF NOT EXISTS bots_updated_at_idx ON bots (updated_at DESC);
CREATE INDEX IF NOT EXISTS messages_thread_seq_idx ON messages (thread_id, seq DESC);
CREATE INDEX IF NOT EXISTS runs_bot_started_idx ON runs (bot_id, started_at DESC);
