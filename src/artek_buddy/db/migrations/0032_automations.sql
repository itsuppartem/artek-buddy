ALTER TABLE routines
    ADD COLUMN IF NOT EXISTS require_approval BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS definition_version INT NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS automations (
    id TEXT PRIMARY KEY,
    routine_id TEXT NOT NULL UNIQUE REFERENCES routines(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    trigger_kind TEXT NOT NULL,
    cron TEXT,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    prompt TEXT NOT NULL,
    require_approval BOOLEAN NOT NULL DEFAULT FALSE,
    definition_version INT NOT NULL DEFAULT 1,
    state TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS automation_steps (
    id TEXT PRIMARY KEY,
    automation_id TEXT NOT NULL REFERENCES automations(id) ON DELETE CASCADE,
    seq INT NOT NULL,
    kind TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (automation_id, seq)
);

CREATE TABLE IF NOT EXISTS automation_runs (
    id TEXT PRIMARY KEY,
    automation_id TEXT NOT NULL REFERENCES automations(id) ON DELETE CASCADE,
    routine_id TEXT NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    definition_version INT NOT NULL,
    trigger_kind TEXT NOT NULL,
    trigger_event_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL,
    snapshot JSONB NOT NULL,
    approval_run_id TEXT,
    thread_run_id TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS automation_step_runs (
    id TEXT PRIMARY KEY,
    automation_run_id TEXT NOT NULL REFERENCES automation_runs(id) ON DELETE CASCADE,
    seq INT NOT NULL,
    kind TEXT NOT NULL,
    state TEXT NOT NULL,
    job_id TEXT,
    safe_output TEXT,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (automation_run_id, seq)
);

CREATE INDEX IF NOT EXISTS automation_runs_routine_idx
    ON automation_runs (routine_id, created_at DESC);

INSERT INTO automations (
    id, routine_id, bot_id, name, trigger_kind, cron, timezone, prompt,
    require_approval, definition_version, state, created_at, updated_at
)
SELECT
    'aut_' || substr(id, 5),
    id,
    bot_id,
    name,
    'cron',
    cron,
    timezone,
    prompt,
    require_approval,
    definition_version,
    CASE WHEN active THEN 'enabled' ELSE 'disabled' END,
    created_at,
    created_at
FROM routines
ON CONFLICT (routine_id) DO NOTHING;

INSERT INTO automation_steps (id, automation_id, seq, kind, config)
SELECT
    'astep_' || substr(a.id, 5) || '_1',
    a.id,
    1,
    'prompt_bot',
    jsonb_build_object('prompt', a.prompt)
FROM automations a
WHERE NOT EXISTS (
    SELECT 1 FROM automation_steps s WHERE s.automation_id = a.id
);
