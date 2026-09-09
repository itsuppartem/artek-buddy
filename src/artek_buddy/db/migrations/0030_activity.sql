-- Workspace-monotonic durable activity log. Sequence is host-global because
-- this deployment is one workspace. EventHub stays the live fan-out; this
-- table is what a reconnect replays. Retention is a count bound
-- (DEFAULT_ACTIVITY_RETENTION), not an audit hash chain (#160).
CREATE TABLE IF NOT EXISTS activity (
    seq BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    event_version INT NOT NULL DEFAULT 1,
    actor TEXT NOT NULL,
    device_id TEXT,
    resource TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS activity_resource_seq_idx ON activity (resource, seq);
CREATE INDEX IF NOT EXISTS activity_event_type_idx ON activity (event_type);
CREATE INDEX IF NOT EXISTS activity_created_at_idx ON activity (created_at);
