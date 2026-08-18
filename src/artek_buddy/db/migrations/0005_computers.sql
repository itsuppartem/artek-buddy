CREATE TABLE IF NOT EXISTS computers (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    scope TEXT NOT NULL,
    scope_key TEXT NOT NULL UNIQUE,
    home_key TEXT NOT NULL UNIQUE,
    home_revision TEXT,
    kind TEXT NOT NULL DEFAULT 'docker',
    provider_ref TEXT,
    state TEXT NOT NULL DEFAULT 'stopped',
    control_holder TEXT NOT NULL DEFAULT 'none',
    control_lease_id TEXT,
    control_lease_expires_at TIMESTAMPTZ,
    control_bot_id TEXT,
    execution_run_id TEXT,
    execution_bot_id TEXT,
    execution_lease_expires_at TIMESTAMPTZ,
    sleep_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE bots ADD COLUMN IF NOT EXISTS computer_id TEXT REFERENCES computers(id);

CREATE INDEX IF NOT EXISTS computers_state_sleep_idx ON computers (state, sleep_at);
CREATE INDEX IF NOT EXISTS bots_computer_id_idx ON bots (computer_id);
