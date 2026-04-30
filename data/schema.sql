-- =============================================================================
-- Reddit bot – database schema for PostgreSQL / Supabase
-- =============================================================================
-- How to use (new project):
--   1. Supabase Dashboard → SQL Editor → New query
--   2. Paste this entire file → Run
-- Safe to re-run: uses IF NOT EXISTS / no-op friendly patterns.
-- The Python worker connects with your DATABASE_URL (direct or pooler).
-- =============================================================================

-- Posts: raw ingested Reddit content (no usernames required; author may be empty)
CREATE TABLE IF NOT EXISTS public.posts (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    external_id     TEXT NOT NULL,
    subreddit       TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    selftext        TEXT NOT NULL DEFAULT '',
    author          TEXT,
    post_url        TEXT,
    created_utc     TIMESTAMPTZ NOT NULL,
    CONSTRAINT posts_source_external_id_key UNIQUE (source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_posts_created_utc ON public.posts (created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON public.posts (subreddit);

-- One classification row per post (upserted by the classifier job)
CREATE TABLE IF NOT EXISTS public.post_classifications (
    id                   BIGSERIAL PRIMARY KEY,
    post_id              BIGINT NOT NULL REFERENCES public.posts (id) ON DELETE CASCADE,
    topic                TEXT,
    sentiment            TEXT,
    emotional_intensity  INTEGER,
    financial_mention    BOOLEAN,
    financial_amount     TEXT,
    problem_category     TEXT,
    intent               TEXT,
    vehicle_make         TEXT,
    vehicle_model        TEXT,
    keywords             TEXT[],
    summary              TEXT,
    suggested_action     TEXT,
    classified_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT post_classifications_post_id_key UNIQUE (post_id)
);

CREATE INDEX IF NOT EXISTS idx_post_classifications_classified_at
    ON public.post_classifications (classified_at DESC);

-- Optional: help the “unclassified” lookup (LEFT JOIN … WHERE c.id IS NULL)
CREATE INDEX IF NOT EXISTS idx_post_classifications_post_id ON public.post_classifications (post_id);

-- Small state table for weekly report locking and estimated OpenAI budget tracking.
CREATE TABLE IF NOT EXISTS public.job_state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
