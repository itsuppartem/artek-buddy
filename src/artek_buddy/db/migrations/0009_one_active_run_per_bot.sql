CREATE UNIQUE INDEX IF NOT EXISTS one_active_run_per_bot
ON runs (bot_id)
WHERE status IN ('queued', 'leased', 'running', 'waiting_input', 'waiting_takeover');
