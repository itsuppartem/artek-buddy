ALTER TABLE subagents ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ;
ALTER TABLE subagents ADD COLUMN IF NOT EXISTS activity_seq BIGINT NOT NULL DEFAULT 0;
ALTER TABLE subagents ADD COLUMN IF NOT EXISTS last_activity_kind TEXT;
ALTER TABLE subagents ADD COLUMN IF NOT EXISTS last_tool_name TEXT;
ALTER TABLE subagents ADD COLUMN IF NOT EXISTS tool_running BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE subagents DROP CONSTRAINT IF EXISTS subagents_activity_kind_chk;
ALTER TABLE subagents ADD CONSTRAINT subagents_activity_kind_chk
    CHECK (
        last_activity_kind IS NULL
        OR last_activity_kind IN (
            'run_started',
            'tool_started',
            'tool_finished',
            'text',
            'clarification'
        )
    );
