ALTER TABLE consent_requests
    ADD COLUMN IF NOT EXISTS job_status TEXT,
    ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

UPDATE consent_requests
SET job_status = 'queued'
WHERE status = 'pending'
  AND action_class IN ('owner_read', 'owner_write', 'owner_exec')
  AND job_status IS NULL;

ALTER TABLE consent_requests
    ADD CONSTRAINT consent_requests_job_status_check
    CHECK (
        job_status IS NULL
        OR job_status IN ('queued', 'acknowledged', 'completed', 'failed', 'timed_out')
    );

CREATE INDEX IF NOT EXISTS consent_requests_owner_job_idx
    ON consent_requests (bot_id, run_id, job_status)
    WHERE message_id IS NULL AND job_status IS NOT NULL;
