ALTER TABLE subagents ADD COLUMN IF NOT EXISTS progress_remaining TEXT;
ALTER TABLE subagents ADD COLUMN IF NOT EXISTS progress_posted_at TIMESTAMPTZ;
ALTER TABLE subagents ADD COLUMN IF NOT EXISTS progress_posted_text TEXT;

ALTER TABLE subagents DROP CONSTRAINT IF EXISTS subagents_activity_kind_chk;
ALTER TABLE subagents ADD CONSTRAINT subagents_activity_kind_chk
    CHECK (
        last_activity_kind IS NULL
        OR last_activity_kind IN (
            'run_started',
            'tool_started',
            'tool_finished',
            'text',
            'clarification',
            'progress'
        )
    );
