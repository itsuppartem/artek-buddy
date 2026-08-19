CREATE TABLE IF NOT EXISTS consent_grants (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    bot_id TEXT NOT NULL REFERENCES bots (id) ON DELETE CASCADE,
    device_id TEXT,
    action_class TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS consent_grants_uniq
    ON consent_grants (bot_id, COALESCE(device_id, ''), action_class, scope_key);

CREATE INDEX IF NOT EXISTS consent_grants_bot_idx
    ON consent_grants (bot_id, action_class);

CREATE TABLE IF NOT EXISTS consent_requests (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    bot_id TEXT NOT NULL REFERENCES bots (id) ON DELETE CASCADE,
    run_id TEXT,
    thread_id TEXT,
    message_id TEXT,
    action_class TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    device_id TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    answered_at TIMESTAMPTZ,
    CHECK (status IN ('pending', 'once', 'always', 'deny'))
);

CREATE INDEX IF NOT EXISTS consent_requests_pending_idx
    ON consent_requests (bot_id, status);
