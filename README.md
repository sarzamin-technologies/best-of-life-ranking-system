# Best of Life — Ranking System

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)

An open-source, **local, monthly** batch pipeline that ranks local businesses on **real
customer satisfaction and service quality** — not ad spend or who collects the most reviews.
It curates topic×neighbourhood pairs, discovers every relevant business from public sources,
collects all publicly available data about them, stores it in a **local Postgres data
warehouse**, scores six weighted pillars, and produces a transparent 0–100 rank per topic
plus AI-written "why it's a good choice" highlights for each business.

It's the ranking engine behind [best-of.life](https://best-of.life). The methodology is
documented in plain language in [WHITEPAPER.md](WHITEPAPER.md).

The pipeline is **standalone**: it writes export artifacts to `exports/<run_id>/` — one JSON
file per topic plus a combined CSV — ready to load into any downstream system.

## Ranking philosophy

Reward **customer satisfaction and service quality**, not just digital presence. A clean,
usable digital channel is one positive pillar, not the whole score.

| Pillar | Signal | Default weight |
|---|---|---|
| Customer Satisfaction | Bayesian-adjusted rating across Google + Yelp, cross-platform consistency | 0.30 |
| Service Quality | review-text NLP: service/staff sentiment, complaint rate, owner-response rate | 0.20 |
| Popularity / Reputation | review volume (log), cross-platform presence, Reddit/web mentions | 0.15 |
| Digital Presence | website existence + Firecrawl SEO/quality, booking/social links | 0.15 |
| Search Visibility | SEMrush authority/traffic + SERP rank for the topic query | 0.10 |
| AI Visibility | LLM recommendation/mention rate for the topic query | 0.10 |

Weights live in `config/weights.yaml` — retune without touching code.

## Setup

```bash
# 1. Python deps (uv recommended; pip works too)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Local Postgres DWH
docker compose up -d
psql postgresql://ranking:ranking@localhost:5544/ranking -f sql/001_dwh.sql

# 3. Keys
cp .env.example .env   # fill in whatever you have; missing sources are skipped
```

## Run

The pipeline is a sequence of idempotent stages — `catalog → discover → collect →
transform → score → strengths → export` — driven by one CLI. A monthly run is `--stage all`.

```bash
# Load the curated catalog (topics + regions) into the DWH
python -m ranking.run --stage catalog

# Discover candidate businesses for one topic (or all)
python -m ranking.run --stage discover --topics best-coffee-downtown-toronto --limit 25

# Collect raw datapoints, normalize, score, export
python -m ranking.run --stage collect   --topics best-coffee-downtown-toronto
python -m ranking.run --stage transform --topics best-coffee-downtown-toronto
python -m ranking.run --stage score     --topics best-coffee-downtown-toronto
python -m ranking.run --stage export    --topics best-coffee-downtown-toronto

# Or everything, for every included topic:
python -m ranking.run --stage all
```

Each run gets a `run_id` (default: `YYYY-MM`, the current month). Re-running the same
`run_id` upserts in place — safe to resume after a failure.

## Layout

```
config/   weights.yaml, topics.seed.yaml (the curated catalog)
sql/      001_dwh.sql (DWH schema)
ranking/  db, models, the six stages, run.py CLI, sources/ (one client per data source)
tests/    deterministic unit tests for transform + score math (no DB needed)
exports/  per-run output artifacts (gitignored)
```

## Tests

```bash
pytest            # transform + score math; no DB or API keys required
```

## Contributing

Issues and pull requests are welcome. Keep the pure-math modules (`transform.py`,
`score.py`) free of DB/network imports so they stay unit-testable, and run `pytest`
before submitting.

## License

Licensed under the Apache License, Version 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
© 2026 Sarzamin Technologies.
