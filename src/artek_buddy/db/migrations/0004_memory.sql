CREATE TABLE IF NOT EXISTS memory_documents (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    bot_id TEXT REFERENCES bots(id) ON DELETE CASCADE,
    scope TEXT NOT NULL,
    path TEXT NOT NULL,
    content TEXT NOT NULL,
    revision INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (scope IN ('bot', 'user')),
    CHECK (
        (scope = 'bot' AND bot_id IS NOT NULL)
        OR (scope = 'user' AND bot_id IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS memory_documents_unique
    ON memory_documents (workspace_id, scope, COALESCE(bot_id, ''), path);

CREATE INDEX IF NOT EXISTS memory_documents_bot_idx
    ON memory_documents (bot_id);

CREATE TABLE IF NOT EXISTS memory_revisions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES memory_documents(id) ON DELETE CASCADE,
    revision INT NOT NULL,
    content TEXT NOT NULL,
    source_run_id TEXT,
    source_thread_id TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (document_id, revision)
);
