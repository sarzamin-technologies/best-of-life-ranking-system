-- Per-business strength bullets ("why it's a good choice"), written by the AI
-- strengths stage from each business's real metrics + review highlights.
--
--   psql "$DWH_DATABASE_URL" -f sql/002_strengths.sql

alter table rankings add column if not exists strengths jsonb not null default '[]'::jsonb;
