ALTER TABLE consent_requests
    ADD COLUMN IF NOT EXISTS parent_run_id TEXT;

CREATE INDEX IF NOT EXISTS consent_requests_parent_run_idx
    ON consent_requests (bot_id, parent_run_id)
    WHERE parent_run_id IS NOT NULL;
