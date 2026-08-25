CREATE TABLE IF NOT EXISTS connection_key (
    id INT PRIMARY KEY CHECK (id = 1),
    api_key TEXT,
    last_four TEXT,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS connections (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL,
    capabilities TEXT[] NOT NULL DEFAULT '{}',
    no_auth BOOLEAN NOT NULL DEFAULT FALSE,
    remote_id TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS connections_active_provider
    ON connections (provider)
    WHERE status IN ('pending', 'connected');
