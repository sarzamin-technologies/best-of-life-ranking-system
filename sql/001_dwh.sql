-- Ontario Ranking — local Postgres data warehouse schema.
-- Mirrors the website's catalog tables (regions, topics) and adds warehouse
-- fact tables. All fact rows are stamped with run_id (one monthly batch), so
-- re-runs are idempotent and history is retained.
--
-- Bootstrap:  psql "$DWH_DATABASE_URL" -f sql/001_dwh.sql

begin;

-- ---------------------------------------------------------------------------
-- Batch runs
-- ---------------------------------------------------------------------------
create table if not exists runs (
  id          text primary key,                 -- e.g. '2026-06' (the month)
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  notes       text
);

-- ---------------------------------------------------------------------------
-- Catalog (mirror of prod Supabase). Loaded from config/topics.seed.yaml.
-- We carry the prod `slug`s verbatim so export maps cleanly back to the site.
-- ---------------------------------------------------------------------------
create table if not exists regions (
  slug         text primary key,
  name         text not null,
  parent_slug  text references regions(slug),
  center_lat   double precision,
  center_lng   double precision,
  search_radius_m integer not null default 4000,
  is_neighbourhood boolean not null default true
);

create table if not exists topics (
  slug         text primary key,
  title        text not null,
  description  text,
  category     text not null,
  region_slug  text not null references regions(slug),
  -- curation metadata (catalog stage)
  hot_score    numeric,
  included     boolean not null default true,
  search_query text                                 -- override Places query if set
);
create index if not exists topics_region_idx on topics(region_slug);
create index if not exists topics_included_idx on topics(included);

-- ---------------------------------------------------------------------------
-- Business master entity (deduped across sources).
-- Crosswalk key = Google place_id; yelp_id / domain are secondary join keys.
-- ---------------------------------------------------------------------------
create table if not exists businesses (
  id                 bigint generated always as identity primary key,
  place_id           text unique,                  -- Google Places id (primary key)
  yelp_id            text,
  name               text not null,
  address            text,
  lat                double precision,
  lng                double precision,
  phone              text,
  website            text,
  domain             text,
  canonical_category text,
  first_seen_run     text references runs(id),
  last_seen_run      text references runs(id),
  created_at         timestamptz not null default now()
);
create index if not exists businesses_yelp_idx on businesses(yelp_id);
create index if not exists businesses_domain_idx on businesses(domain);

-- ---------------------------------------------------------------------------
-- Which businesses compete in which topic×neighbourhood pair (M:N).
-- ---------------------------------------------------------------------------
create table if not exists business_topics (
  business_id     bigint not null references businesses(id) on delete cascade,
  topic_slug      text not null references topics(slug) on delete cascade,
  run_id          text not null references runs(id),
  discovered_via  text not null,                   -- google_places | yelp | web_search | reddit
  discovery_query text,
  distance_m      double precision,
  created_at      timestamptz not null default now(),
  primary key (business_id, topic_slug, run_id)
);
create index if not exists business_topics_topic_idx on business_topics(topic_slug, run_id);

-- ---------------------------------------------------------------------------
-- Raw API responses — full audit trail, one row per (business, source, run).
-- ---------------------------------------------------------------------------
create table if not exists raw_collections (
  id           bigint generated always as identity primary key,
  business_id  bigint not null references businesses(id) on delete cascade,
  source       text not null,                      -- google_places | yelp | firecrawl | semrush | web_search | reddit | ai_search
  run_id       text not null references runs(id),
  collected_at timestamptz not null default now(),
  payload      jsonb not null default '{}'::jsonb,
  unique (business_id, source, run_id)
);
create index if not exists raw_collections_run_idx on raw_collections(run_id, source);

-- ---------------------------------------------------------------------------
-- Normalized numeric signals extracted from raw (the "metrics" / EAV layer).
-- Topic-scoped because some signals (SERP rank, AI mention) depend on the query.
-- ---------------------------------------------------------------------------
create table if not exists metrics (
  business_id bigint not null references businesses(id) on delete cascade,
  topic_slug  text not null references topics(slug) on delete cascade,
  run_id      text not null references runs(id),
  metric_key  text not null,                        -- e.g. 'google.rating', 'nlp.service_sentiment'
  value       numeric,
  source      text,
  meta        jsonb not null default '{}'::jsonb,
  primary key (business_id, topic_slug, run_id, metric_key)
);
create index if not exists metrics_topic_idx on metrics(topic_slug, run_id, metric_key);

-- ---------------------------------------------------------------------------
-- Per-pillar sub-scores, normalized WITHIN each topic.
-- ---------------------------------------------------------------------------
create table if not exists pillar_scores (
  business_id      bigint not null references businesses(id) on delete cascade,
  topic_slug       text not null references topics(slug) on delete cascade,
  run_id           text not null references runs(id),
  pillar           text not null,                   -- satisfaction | service | popularity | digital | search | ai
  raw_score        numeric,                         -- 0..100 absolute
  normalized_score numeric,                         -- 0..100 within-topic
  primary key (business_id, topic_slug, run_id, pillar)
);
create index if not exists pillar_scores_topic_idx on pillar_scores(topic_slug, run_id, pillar);

-- ---------------------------------------------------------------------------
-- Final ranking output — the export reads from here.
-- ---------------------------------------------------------------------------
create table if not exists rankings (
  topic_slug       text not null references topics(slug) on delete cascade,
  business_id      bigint not null references businesses(id) on delete cascade,
  run_id           text not null references runs(id),
  final_score      numeric not null,                -- 0..100
  rank_position    integer not null,                -- 1 = best, within topic
  pillar_breakdown jsonb not null default '{}'::jsonb,
  created_at       timestamptz not null default now(),
  primary key (topic_slug, business_id, run_id)
);
create index if not exists rankings_rank_idx on rankings(topic_slug, run_id, rank_position);

commit;
