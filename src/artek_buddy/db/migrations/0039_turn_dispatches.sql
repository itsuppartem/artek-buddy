CREATE TABLE IF NOT EXISTS turn_dispatches (
    run_id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS turn_dispatches_pending
    ON turn_dispatches (state)
    WHERE state = 'pending';
