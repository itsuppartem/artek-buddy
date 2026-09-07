CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    resource_id TEXT,
    idempotency_key TEXT UNIQUE,
    state TEXT NOT NULL DEFAULT 'queued',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB,
    last_error TEXT,
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS jobs_claim_idx ON jobs (state, run_at, lease_expires_at) WHERE state = 'queued';
CREATE INDEX IF NOT EXISTS jobs_running_claim_idx ON jobs (state, lease_expires_at) WHERE state = 'running';
CREATE INDEX IF NOT EXISTS jobs_type_resource_idx ON jobs (job_type, resource_id);
CREATE INDEX IF NOT EXISTS jobs_dead_idx ON jobs (state) WHERE state = 'dead';
