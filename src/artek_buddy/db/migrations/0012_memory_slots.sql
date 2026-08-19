ALTER TABLE memory_entries
    ADD COLUMN IF NOT EXISTS slot TEXT;

CREATE INDEX IF NOT EXISTS memory_entries_slot_idx
    ON memory_entries (workspace_id, scope, slot)
    WHERE superseded_at IS NULL AND slot IS NOT NULL;
