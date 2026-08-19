CREATE TABLE IF NOT EXISTS memory_entries (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
    scope TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    source TEXT NOT NULL,
    source_run_id TEXT,
    source_thread_id TEXT,
    document_id TEXT REFERENCES memory_documents(id) ON DELETE SET NULL,
    superseded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (scope IN ('bot', 'user')),
    CHECK (
        (scope = 'bot' AND bot_id IS NOT NULL)
        OR (scope = 'user')
    )
);

CREATE INDEX IF NOT EXISTS memory_entries_live_idx
    ON memory_entries (workspace_id, scope, superseded_at);

CREATE INDEX IF NOT EXISTS memory_entries_bot_idx
    ON memory_entries (bot_id);
