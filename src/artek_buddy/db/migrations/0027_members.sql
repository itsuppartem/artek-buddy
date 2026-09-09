CREATE TABLE IF NOT EXISTS members (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'owner',
    state TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bootstrap exactly one owner member if not present
INSERT INTO members (id, name, role, state, created_at, updated_at)
VALUES ('mem_owner', 'Owner', 'owner', 'active', now(), now())
ON CONFLICT (id) DO NOTHING;

-- Bind devices to members
ALTER TABLE devices ADD COLUMN IF NOT EXISTS member_id TEXT REFERENCES members(id);

-- Bind existing unrevoked and revoked devices to the owner member
UPDATE devices SET member_id = 'mem_owner' WHERE member_id IS NULL;

CREATE INDEX IF NOT EXISTS devices_member_id_idx ON devices (member_id);
CREATE INDEX IF NOT EXISTS members_state_idx ON members (state);
