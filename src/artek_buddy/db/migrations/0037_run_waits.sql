CREATE TABLE IF NOT EXISTS run_waits (
    run_id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    effect TEXT NOT NULL,
    message_id TEXT,
    consent_id TEXT,
    recovered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);

ALTER TABLE run_waits
    ADD CONSTRAINT run_waits_kind_check
    CHECK (kind IN ('ask', 'consent', 'takeover', 'owner_job', 'running'));

ALTER TABLE run_waits
    ADD CONSTRAINT run_waits_path_check
    CHECK (path IN ('continue', 'check', 'new_attempt'));

ALTER TABLE run_waits
    ADD CONSTRAINT run_waits_effect_check
    CHECK (effect IN ('intended', 'completed', 'failed', 'ambiguous', 'reconciled'));
