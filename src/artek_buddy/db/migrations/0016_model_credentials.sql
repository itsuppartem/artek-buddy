CREATE TABLE IF NOT EXISTS model_credentials (
    provider TEXT PRIMARY KEY,
    api_key TEXT,
    last_four TEXT,
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS model_defaults (
    id INT PRIMARY KEY CHECK (id = 1),
    provider TEXT,
    model_id TEXT
);

CREATE TABLE IF NOT EXISTS model_catalog (
    provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    PRIMARY KEY (provider, model_id)
);
