ALTER TABLE memory_entries
    ADD COLUMN IF NOT EXISTS shelf TEXT NOT NULL DEFAULT 'owner';

ALTER TABLE memory_entries
    ADD COLUMN IF NOT EXISTS until TIMESTAMPTZ;

ALTER TABLE memory_entries
    DROP CONSTRAINT IF EXISTS memory_entries_shelf_check;

ALTER TABLE memory_entries
    ADD CONSTRAINT memory_entries_shelf_check
    CHECK (shelf IN ('owner', 'work', 'charter'));

CREATE INDEX IF NOT EXISTS memory_entries_shelf_idx
    ON memory_entries (workspace_id, shelf, superseded_at);
