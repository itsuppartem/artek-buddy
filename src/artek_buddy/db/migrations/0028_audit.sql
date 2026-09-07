CREATE TABLE IF NOT EXISTS audit (
    seq BIGINT PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    resource TEXT NOT NULL,
    payload JSONB NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_event_type_idx ON audit (event_type);
CREATE INDEX IF NOT EXISTS audit_created_at_idx ON audit (created_at);
