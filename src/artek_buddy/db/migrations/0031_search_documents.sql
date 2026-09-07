-- Permission-aware full-text projection. Rank/headline/limit must always
-- filter by resource_id first; GIN is not a leakproof RLS policy.
CREATE TABLE IF NOT EXISTS search_documents (
    id TEXT PRIMARY KEY,
    document_kind TEXT NOT NULL,
    resource_kind TEXT NOT NULL DEFAULT 'bot',
    resource_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    language_config TEXT NOT NULL DEFAULT 'simple',
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(body, ''))
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    UNIQUE (document_kind, source_id)
);

CREATE INDEX IF NOT EXISTS search_documents_vector_idx
    ON search_documents USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS search_documents_resource_live_idx
    ON search_documents (resource_id)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS search_documents_kind_live_idx
    ON search_documents (document_kind)
    WHERE deleted_at IS NULL;
