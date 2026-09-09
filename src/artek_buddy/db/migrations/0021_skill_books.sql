CREATE TABLE IF NOT EXISTS skill_books (
    id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    when_to_use TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS skill_books_bot_slug
    ON skill_books (bot_id, slug);

CREATE INDEX IF NOT EXISTS skill_books_bot_updated
    ON skill_books (bot_id, updated_at DESC);
