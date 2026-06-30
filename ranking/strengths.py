"""Stage 5b — write 3-5 strength bullets per ranked business ("why it's a good
choice"), grounded in its real metrics + review highlights, via Agnic AI.

Runs after `score` (needs rankings + metrics + raw reviews, all already collected).
Resilient + per-business commit, and AI calls are disk-cached, so it's cheap and
resumable. Stored in `rankings.strengths`, then carried to the site by export/import.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Sequence

from . import db, transform
from .config import SourceKeys
from .sources import ai_search

log = logging.getLogger("ranking.strengths")

# Pillar codes -> human labels for the AI context.
PILLAR_LABELS = {
    "satisfaction": "customer_satisfaction", "service": "service_quality",
    "popularity": "popularity", "digital": "digital_presence",
    "search": "search_visibility", "ai": "ai_visibility",
}


def _context(rank_row: Dict[str, Any], metrics: Dict[str, float],
             review_snips: List[str], run_id: str) -> Dict[str, Any]:
    """Build the compact, factual context the model writes bullets from."""
    pillars = rank_row.get("pillar_breakdown") or {}
    ctx: Dict[str, Any] = {
        "run_id": run_id,
        "business_id": rank_row["business_id"],
        "name": rank_row["name"],
        "rank_position": rank_row["rank_position"],
        "ranking_score": round(float(rank_row["final_score"]), 1),
        "google_rating": metrics.get("google.rating"),
        "google_review_count": int(metrics["google.review_count"]) if metrics.get("google.review_count") else None,
        "yelp_rating": metrics.get("yelp.rating"),
        "yelp_review_count": int(metrics["yelp.review_count"]) if metrics.get("yelp.review_count") else None,
        "pillar_percentiles": {PILLAR_LABELS.get(k, k): round(v) for k, v in pillars.items()},
        "review_highlights": review_snips[:6],
    }
    # Drop empty keys so the prompt stays tight and the model isn't tempted to invent.
    return {k: v for k, v in ctx.items() if v not in (None, [], {}, "")}


def run_strengths(topics: Sequence[str], run_id: str) -> None:
    keys = SourceKeys()
    if not ai_search.enabled(keys):
        print("  strengths skipped: no AI key configured")
        return

    with db.connect() as conn:
        for topic in topics:
            ranked = db.ranking_for_topic(conn, topic, run_id)
            if not ranked:
                continue
            # Index metrics + review snippets by business for this topic.
            metric_rows = db.metrics_for_topic(conn, topic, run_id)
            metrics_by_biz: Dict[int, Dict[str, float]] = {}
            for m in metric_rows:
                if m["value"] is not None:
                    metrics_by_biz.setdefault(m["business_id"], {})[m["metric_key"]] = float(m["value"])
            snips_by_biz = _review_snippets(db.raw_for_topic(conn, topic, run_id))

            done = 0
            for row in ranked:
                bid = row["business_id"]
                try:
                    ctx = _context(row, metrics_by_biz.get(bid, {}), snips_by_biz.get(bid, []), run_id)
                    bullets = ai_search.write_strengths(keys, ctx)
                    if bullets:
                        db.set_strengths(conn, topic, bid, run_id, bullets)
                        conn.commit()
                        done += 1
                except Exception as e:  # pragma: no cover - network
                    conn.rollback()
                    log.warning("strengths %s (%s) failed: %s", bid, row.get("name"), str(e)[:140])
            print("  strengths %-43s %3d/%d businesses" % (topic, done, len(ranked)))


def _review_snippets(raws: List[Dict[str, Any]]) -> Dict[int, List[str]]:
    """Per business, a few short positive-leaning review excerpts to ground bullets."""
    by_biz: Dict[int, List[str]] = {}
    grouped: Dict[int, Dict[str, Any]] = {}
    for r in raws:
        grouped.setdefault(r["business_id"], {})[r["source"]] = r["payload"]
    for bid, sources in grouped.items():
        texts = transform._google_review_texts(sources.get("google_places") or {}) \
            + transform._yelp_review_texts(sources.get("yelp") or {})
        # shortest-first keeps snippets tight; cap length so prompts stay small
        clean = [t.strip().replace("\n", " ")[:200] for t in texts if t and len(t.strip()) > 20]
        clean.sort(key=len)
        if clean:
            by_biz[bid] = clean[:6]
    return by_biz
