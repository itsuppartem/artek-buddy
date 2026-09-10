CREATE TABLE IF NOT EXISTS owner_commands (
    command_id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    run_id TEXT NOT NULL,
    message_id TEXT,
    parent_command_id TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS owner_commands_bot_id ON owner_commands (bot_id);
CREATE INDEX IF NOT EXISTS owner_commands_run_id ON owner_commands (run_id);
