"""Stage 1 — load + curate the topic×neighbourhood catalog into the DWH.

`run_catalog()` loads config/topics.seed.yaml (regions + the curated topics,
seeded from the website's original 100 pairs). With --curate it additionally asks
the LLM to nominate high-demand "hot" pairs per neighbourhood, scores each by Google
Places result density, and writes them back as `included = false` suggestions plus a
review file under exports/<run_id>/ for a human to promote.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import yaml

from . import config, db
from .config import SourceKeys
from .sources import ai_search, google_places


def _seed_query(topic: Dict[str, Any], region_name: str) -> str:
    if topic.get("search_query"):
        return topic["search_query"]
    title = topic["title"]
    # "Best Coffee Shop in Downtown Toronto" -> "Coffee Shop in <region>, Ontario, Canada"
    core = title
    for prefix in ("Best ", "best "):
        if core.startswith(prefix):
            core = core[len(prefix):]
    if " in " in core:
        core = core.rsplit(" in ", 1)[0]
    return "%s in %s, Ontario, Canada" % (core.strip(), region_name)


def run_catalog(run_id: str, curate: bool = False) -> None:
    cat = config.catalog()
    regions: List[Dict[str, Any]] = cat.get("regions", [])
    topics: List[Dict[str, Any]] = cat.get("topics", [])

    with db.connect() as conn:
        db.ensure_run(conn, run_id, "catalog load")
        for r in regions:
            db.upsert_region(conn, r)
        for t in topics:
            db.upsert_topic(conn, t)
        print("  catalog loaded %d regions, %d topics" % (len(regions), len(topics)))

    if curate:
        _curate_hot_pairs(run_id, regions)


def _curate_hot_pairs(run_id: str, regions: List[Dict[str, Any]]) -> None:
    keys = SourceKeys()
    if not ai_search.enabled(keys):
        print("  curate skipped: no AI key configured")
        return
    region_names = {r["slug"]: r["name"] for r in regions}
    suggestions: List[Dict[str, Any]] = []

    with db.connect() as conn:
        for r in regions:
            if not r.get("is_neighbourhood"):
                continue
            ideas = ai_search.nominate_hot_pairs(keys, r["name"], n=10)
            for idea in ideas:
                hot = _demand_score(keys, idea["title"], r)
                slug = _slugify("%s %s" % (idea["title"], r["slug"]))
                topic = {
                    "slug": slug,
                    "title": idea["title"] if idea["title"].lower().startswith("best")
                    else "Best %s in %s" % (idea["title"], r["name"]),
                    "category": idea.get("category", "food"),
                    "region_slug": r["slug"],
                    "hot_score": hot,
                    "included": False,  # human promotes after review
                }
                db.upsert_topic(conn, topic)
                suggestions.append(topic)

    suggestions.sort(key=lambda t: t.get("hot_score") or 0, reverse=True)
    out_dir = os.path.join(config.EXPORTS_DIR, run_id)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "hot_pairs_suggestions.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"topics": suggestions}, fh, sort_keys=False, allow_unicode=True)
    print("  curate: %d suggestions -> %s (review, then set included: true)"
          % (len(suggestions), path))


def _demand_score(keys: SourceKeys, title: str, region: Dict[str, Any]) -> float:
    """Cheap proxy for demand/competition: how many real businesses Google
    returns for the query (more candidates -> hotter, more useful to rank)."""
    if not google_places.enabled(keys):
        return 0.0
    q = "%s in %s, Ontario, Canada" % (title, region["name"])
    res = google_places.search_text(keys, q, region.get("center_lat"), region.get("center_lng"),
                                    radius_m=region.get("search_radius_m", 4000), max_results=20)
    rated = [c for c in res if c.get("name")]
    return float(len(rated))


def _slugify(s: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:80] or "topic"
